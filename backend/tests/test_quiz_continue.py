import json
from datetime import date

from fastapi.testclient import TestClient

from app import ai, db, importer
from app.main import app


def _entry2():
    return {
        "id": "XF-002", "subject": "刑法", "submodule": "总则-犯罪形态",
        "point": "正当防卫限度",
        "anchor": "甲为阻止乙持刀行凶，反击致乙重伤，属于正当防卫限度内",
        "conclusion": "属于正当防卫，不负刑事责任。", "priority": "高频考点",
        "rationale": "高频",
        "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                     "loc": "为了使国家、公共利益、本人或者他人的人身、财产和其他权利"}],
        "statutes": ["刑法20条"], "note": None, "tts_override": None,
        "tts_text": "【刑法·正当防卫限度】甲为阻止乙持刀行凶……",
    }


def _make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)
    db_path = tmp_path / "quiz.db"
    conn = db.connect(db_path)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final",
        "generated_at": "x", "count": 1,
        "entries": [{
            "id": "XF-001", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": "转化型抢劫",
            "anchor": "甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤",
            "conclusion": "成立抢劫罪。", "priority": "高频考点",
            "rationale": "高频",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": ["刑法269条"],
            "note": None, "tts_override": None,
            "tts_text": "【刑法·转化型抢劫】甲盗窃后……成立抢劫罪。",
        }],
    })
    conn.commit()
    conn.close()

    def override_get_db():
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[db.get_db] = override_get_db
    return TestClient(app), db_path


def _insert_quiz(db_path, answer="AB", analysis="解析：AB 正确。"):
    conn = db.connect(db_path)
    conn.execute(
        "INSERT INTO quizzes (entry_id, qtype, stem, options, answer, analysis, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("XF-001", "choice", "以下哪些说法正确？",
         '["A. 甲对", "B. 乙对", "C. 丙对", "D. 丁对"]',
         answer, analysis, "2026-08-29T00:00:00"),
    )
    conn.commit()
    qid = conn.execute("SELECT id FROM quizzes WHERE entry_id='XF-001'").fetchone()["id"]
    conn.close()
    return qid


def test_quiz_multi_answer_normalized(tmp_path, monkeypatch):
    """多选判题：用户答案 BA 与正确答案 AB 视为一致，且返回解析。"""
    client, db_path = _make_client(tmp_path, monkeypatch)
    qid = _insert_quiz(db_path)
    r = client.post("/api/quiz/answer", json={"quiz_id": qid, "user_answer": "BA"})
    assert r.status_code == 200
    data = r.json()
    assert data["correct"] is True
    assert data["answer"] == "AB"
    assert data["analysis"] == "解析：AB 正确。"


def test_quiz_multi_wrong(tmp_path, monkeypatch):
    client, db_path = _make_client(tmp_path, monkeypatch)
    qid = _insert_quiz(db_path)
    r = client.post("/api/quiz/answer", json={"quiz_id": qid, "user_answer": "AC"})
    assert r.json()["correct"] is False


def test_quiz_analysis_stored(tmp_path, monkeypatch):
    client, db_path = _make_client(tmp_path, monkeypatch)
    qid = _insert_quiz(db_path)
    conn = db.connect(db_path)
    row = conn.execute("SELECT analysis FROM quizzes WHERE id=?", (qid,)).fetchone()
    conn.close()
    assert row["analysis"] == "解析：AB 正确。"


def test_quiz_today_has_analysis(tmp_path, monkeypatch):
    """每日自测题必须带解析（cloze 兜底解析=结论）。"""
    client, _ = _make_client(tmp_path, monkeypatch)
    data = client.get("/api/quiz/today").json()
    assert data["questions"]
    assert all(q["analysis"] for q in data["questions"])


def test_plans_continue_excludes_today(tmp_path, monkeypatch):
    client, db_path = _make_client(tmp_path, monkeypatch)
    conn = db.connect(db_path)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final",
        "generated_at": "x", "count": 1, "entries": [_entry2()],
    })
    # 固定今日计划只含 XF-001，使 XF-002 成为续学候选
    conn.execute(
        "INSERT OR REPLACE INTO daily_plans (date, items, quota, rationale) VALUES (?,?,?,?)",
        (date.today().isoformat(),
         json.dumps([{"entry_id": "XF-001", "bucket": "new"}], ensure_ascii=False),
         1, "test"),
    )
    conn.commit()
    conn.close()
    today_ids = {it["id"] for it in client.get("/api/plans/today").json()["items"]}
    data = client.post("/api/plans/continue", json={"count": 5}).json()
    assert data["items"]
    assert all(it["id"] not in today_ids for it in data["items"])
    assert len(data["items"]) <= 5


def test_listen_more_excludes(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch)
    r = client.post("/api/listen/more", json={"count": 3, "exclude": ["XF-001"]})
    assert r.status_code == 200
    data = r.json()
    assert "remaining" in data
    assert all(it["id"] != "XF-001" for it in data["items"])
