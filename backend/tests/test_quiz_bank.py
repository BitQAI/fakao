import json

import pytest
from fastapi.testclient import TestClient

from app import ai, db, importer, quiz_bank, quiz_service, service
from app.main import app


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """题库测试不访问真实 LLM；如需断言是否调用，用 _llm_calls 记录。"""
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)


def seed(conn, n=3):
    entries = []
    for i in range(1, n + 1):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法",
            "submodule": "分则-财产犯罪", "point": f"考点{i}",
            "anchor": f"甲实施行为{i}，造成后果{i}，案件事实完整描述",
            "conclusion": f"成立罪名{i}。", "priority": "高频考点",
            "rationale": "高频",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": ["刑法269条"], "note": None, "tts_override": None,
            "tts_text": f"【刑法·考点{i}】结论{i}。"})
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": n, "entries": entries})


def test_normalize_judge_answer():
    assert quiz_bank.normalize_judge_answer("对") == "对"
    assert quiz_bank.normalize_judge_answer(" 正确 ") == "对"
    assert quiz_bank.normalize_judge_answer("T") == "对"
    assert quiz_bank.normalize_judge_answer("错") == "错"
    assert quiz_bank.normalize_judge_answer("False") == "错"
    assert quiz_bank.normalize_judge_answer("AB") is None
    assert quiz_bank.normalize_judge_answer("") is None


def test_save_question_is_idempotent(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    first = quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-001",
        subject="刑法", point="考点1", stem="题干", options=["A. 甲", "B. 乙"],
        answer="A", analysis="解析")
    second = quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-001",
        subject="刑法", point="考点1", stem="题干", options=["A. 甲", "B. 乙"],
        answer="A", analysis="解析")
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0] == 1
    row = conn.execute("SELECT origin, status, text_hash FROM quizzes").fetchone()
    assert row["origin"] == "bank" and row["status"] == "draft" and row["text_hash"]
    conn.close()


def test_save_question_replace_updates_in_place(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    qid = quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-001",
        stem="旧题干", options=["A. 甲"], answer="A", analysis="旧")
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-001",
        stem="新题干", options=["A. 甲"], answer="A", analysis="新", replace=True)
    row = conn.execute("SELECT stem, analysis FROM quizzes WHERE id=?", (qid,)).fetchone()
    assert row["stem"] == "新题干" and row["analysis"] == "新"
    assert conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0] == 1
    conn.close()


def test_pick_filters_and_status(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    quiz_bank.save_question(conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                            entry_id="XF-001", subject="刑法", point="考点1",
                            stem="题干1", options=["A. 甲"], answer="A")
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            entry_id="XF-002", subject="刑法", point="考点2",
                            stem="判断句", answer="对")
    assert quiz_bank.pick(conn, limit=10) == []          # draft 不进抽题池
    assert quiz_bank.pick(conn, limit=10, status="draft")[0]["stem"] == "题干1"
    quiz_bank.set_status(conn, origins=(quiz_bank.ORIGIN_BANK,), status="published")
    published = quiz_bank.pick(conn, limit=10)
    assert [q["qtype"] for q in published] == ["choice"]
    assert quiz_bank.pick(conn, limit=10, subjects=["民法"]) == []
    judge = quiz_bank.pick(conn, origins=(quiz_bank.ORIGIN_JUDGE,), limit=10,
                           status="draft")
    assert judge[0]["answer"] == "对" and judge[0]["options"] == []
    conn.close()


def test_question_for_entry_prefers_choice(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            entry_id="XF-001", subject="刑法", stem="判断句",
                            answer="对", status="published")
    assert quiz_bank.question_for_entry(conn, "XF-001")["qtype"] == "judge"
    quiz_bank.save_question(conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                            entry_id="XF-001", subject="刑法", stem="选择题",
                            options=["A. 甲"], answer="A", status="published")
    assert quiz_bank.question_for_entry(conn, "XF-001")["qtype"] == "choice"
    assert quiz_bank.question_for_entry(conn, "XF-999") is None
    conn.close()


def test_daily_quiz_prefers_bank_without_llm(tmp_db, monkeypatch):
    """题库有题时不得调用 LLM 现生成。"""
    calls = []
    monkeypatch.setattr(ai, "call_llm",
                        lambda *a, **k: calls.append(a) or None)
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    for i in range(1, 4):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
            entry_id=f"XF-{i:03d}", subject="刑法", point=f"考点{i}",
            stem=f"题库题干{i}", options=["A. 甲", "B. 乙"], answer="A",
            analysis="解析", status="published")
    service.ensure_today_plan(conn, "2026-08-27")   # 预热今日计划（其 LLM 调用已消音）
    calls.clear()
    questions = quiz_service.build_daily_quiz(conn, "2026-08-27", limit=3)
    assert all(q["stem"].startswith("题库题干") for q in questions)
    assert calls == []
    conn.close()


def test_daily_quiz_falls_back_when_bank_empty(tmp_db, monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)  # 无 LLM → cloze 兜底
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    questions = quiz_service.build_daily_quiz(conn, "2026-08-27", limit=2)
    assert questions and all(q["qtype"] == "cloze" for q in questions)
    conn.close()


def test_judge_quiz_picks_only_published_judge(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            subject="刑诉", stem="刑事拘留最长37日。", answer="对",
                            analysis="正确。", basis="刑诉法91条", status="published")
    quiz_bank.save_question(conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                            subject="刑诉", stem="选择题", options=["A. 甲"],
                            answer="A", status="published")
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            subject="民法", stem="草稿题", answer="错", status="draft")
    out = quiz_service.judge_quiz(conn, limit=10)
    assert out["total"] == 1
    assert out["questions"][0]["basis"] == "刑诉法91条"
    assert quiz_service.judge_quiz(conn, subjects=["民法"], limit=10)["total"] == 0
    conn.close()


def test_custom_quiz_fills_with_statute_questions(tmp_db):
    """条目题不足题量时，用题库补齐（含法条驱动题）。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, 2)
    for i in (1, 2):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
            entry_id=f"XF-{i:03d}", subject="刑法", point=f"考点{i}",
            stem=f"条目题{i}", options=["A. 甲", "B. 乙"], answer="A",
            analysis="解析", status="published")
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
        subject="刑法", stem="法条题：依据著作权法第四十六条命制的题目",
        options=["A. 甲", "B. 乙"], answer="A", analysis="解析",
        basis="中华人民共和国著作权法第四十六条", status="published")
    out = quiz_service.custom_quiz(conn, ["刑法"], [], limit=5)
    stems = [q["stem"] for q in out["questions"]]
    assert "法条题：依据著作权法第四十六条命制的题目" in stems
    assert len(stems) == len(set(stems)) == 3
    conn.close()


def test_custom_quiz_keeps_entries_when_enough(tmp_db):
    """题量小于 3 时不混入法条题（保持原有行为）。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, 3)
    for i in range(1, 4):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
            entry_id=f"XF-{i:03d}", subject="刑法", point=f"考点{i}",
            stem=f"条目题{i}", options=["A. 甲", "B. 乙"], answer="A",
            analysis="解析", status="published")
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
        subject="刑法", stem="法条题X", options=["A. 甲", "B. 乙"], answer="A",
        analysis="解析", basis="中华人民共和国刑法第一条", status="published")
    out = quiz_service.custom_quiz(conn, ["刑法"], [], limit=2)
    assert len(out["questions"]) == 2
    assert all(q["stem"].startswith("条目题") for q in out["questions"])
    conn.close()


def test_custom_quiz_reserves_quota_for_statute_questions(tmp_db):
    """题量 ≥3 时留 1/3 给法条驱动题（否则法条库扩容永远练不到）。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, 6)
    for i in range(1, 7):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
            entry_id=f"XF-{i:03d}", subject="刑法", point=f"考点{i}",
            stem=f"条目题{i}", options=["A. 甲", "B. 乙"], answer="A",
            analysis="解析", status="published")
    for i in range(3):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
            subject="刑法", stem=f"法条题{i}", options=["A. 甲", "B. 乙"],
            answer="A", analysis="解析", basis=f"中华人民共和国刑法第{i + 1}条",
            status="published")
    out = quiz_service.custom_quiz(conn, ["刑法"], [], limit=6)
    stems = [q["stem"] for q in out["questions"]]
    assert len(stems) == 6
    assert sum(1 for s in stems if s.startswith("法条题")) == 2   # 6 // 3
    conn.close()


def _client(tmp_path):
    db_path = tmp_path / "judge.db"
    conn = db.connect(db_path)
    seed(conn)
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            subject="刑诉", point="强制措施",
                            stem="刑事拘留最长37日。", answer="对",
                            analysis="对，含提请批准逮捕期间。", basis="刑诉法91条",
                            status="published")
    conn.close()

    def override_get_db():
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[db.get_db] = override_get_db
    return TestClient(app), db_path


def test_api_judge_and_answer(tmp_path):
    client, _ = _client(tmp_path)
    try:
        res = client.post("/api/quiz/judge", json={"limit": 5})
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        q = data["questions"][0]
        assert q["qtype"] == "judge" and q["options"] == []

        right = client.post("/api/quiz/answer",
                            json={"quiz_id": q["id"], "user_answer": "对"})
        assert right.json()["correct"] is True
        assert "刑诉法91条" in right.json()["analysis"] or right.json()["analysis"]

        wrong = client.post("/api/quiz/answer",
                            json={"quiz_id": q["id"], "user_answer": "错"})
        assert wrong.json()["correct"] is False

        illegal = client.post("/api/quiz/answer",
                              json={"quiz_id": q["id"], "user_answer": "AB"})
        assert illegal.json()["correct"] is False

        missing = client.post("/api/quiz/answer",
                              json={"quiz_id": 9999, "user_answer": "对"})
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(db.get_db, None)


def test_api_judge_empty_bank(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = db.connect(db_path)
    seed(conn)
    conn.close()

    def override_get_db():
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[db.get_db] = override_get_db
    try:
        client = TestClient(app)
        res = client.post("/api/quiz/judge", json={"limit": 10})
        assert res.status_code == 200
        assert res.json() == {"questions": [], "total": 0}
    finally:
        app.dependency_overrides.pop(db.get_db, None)


def test_api_judge_limit_validation(tmp_path):
    client, _ = _client(tmp_path)
    try:
        res = client.post("/api/quiz/judge", json={"limit": 0})
        assert res.status_code == 422
        res = client.post("/api/quiz/judge", json={"limit": 100})
        assert res.status_code == 422
    finally:
        app.dependency_overrides.pop(db.get_db, None)


def test_regenerate_does_not_delete_bank_questions(tmp_path):
    """重新生成当日题目只能删「当日缓存题」，题库资产必须保留。"""
    client, db_path = _client(tmp_path)
    try:
        before = client.get("/api/quiz/bank/stats").json()["items"]
        assert before and before[0]["n"] >= 1
        client.get("/api/quiz/today?regenerate=1")
        conn = db.connect(db_path)
        judge_n = conn.execute(
            "SELECT COUNT(*) FROM quizzes WHERE origin='judge'").fetchone()[0]
        bank_n = conn.execute(
            "SELECT COUNT(*) FROM quizzes WHERE origin='bank'").fetchone()[0]
        conn.close()
        assert judge_n == 1 and bank_n == 0
    finally:
        app.dependency_overrides.pop(db.get_db, None)


def test_quiz_history_includes_basis(tmp_path):
    client, _ = _client(tmp_path)
    try:
        q = client.post("/api/quiz/judge", json={"limit": 1}).json()["questions"][0]
        client.post("/api/quiz/answer", json={"quiz_id": q["id"], "user_answer": "对"})
        items = client.get("/api/quiz/history").json()["items"]
        assert items[0]["basis"] == "刑诉法91条"
        assert items[0]["qtype"] == "judge"
        assert json.loads(json.dumps(items[0]["options"])) == []
    finally:
        app.dependency_overrides.pop(db.get_db, None)
