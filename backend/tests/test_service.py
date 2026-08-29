from datetime import date

import pytest

from app import ai, quiz_service
from app import db, importer, service


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """服务层测试不访问真实 DeepSeek，AI 一律走规则兜底（确定性）。"""
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)


def seed(conn, n=5):
    entries = []
    for i in range(1, n + 1):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": f"考点{i}", "anchor": f"甲实施行为{i}，造成后果{i}，案件事实完整描述",
            "conclusion": f"成立罪名{i}。", "priority": "高频考点",
            "rationale": "高频", "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                                              "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": ["刑法269条"], "note": None, "tts_override": None,
            "tts_text": f"【刑法·考点{i}】结论{i}。"})
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": n, "entries": entries})


def test_ensure_today_plan_generates(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    plan = service.ensure_today_plan(conn, "2026-08-27")
    assert plan["quota"] == 5
    assert plan["counts"]["new"] == 5
    assert plan["items"][0]["bucket"] == "new"
    assert plan["items"][0]["point"] == "考点1"
    assert "距考试" in plan["rationale"] or plan["rationale"]


def test_plan_not_regenerated_when_exists(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    first = service.ensure_today_plan(conn, "2026-08-27")
    conn.execute("UPDATE daily_plans SET rationale='已修改' WHERE date='2026-08-27'")
    conn.commit()
    second = service.ensure_today_plan(conn, "2026-08-27")
    assert second["rationale"] == "已修改"


def test_record_review_and_coverage(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.record_review(conn, "XF-001", "read", "bad")
    service.record_review(conn, "XF-001", "read", "good")
    tree = service.coverage_payload(conn)
    point_state = tree["刑法"]["submodules"]["分则-财产犯罪"]["points"]["考点1"]
    # 两次复习且末次 good → coverage.entry_state 返回 mastered（与 coverage spec 一致）
    assert point_state == "mastered"


def test_build_daily_quiz_falls_back_to_cloze(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.ensure_today_plan(conn, "2026-08-27")
    questions = quiz_service.build_daily_quiz(conn, "2026-08-27")
    assert questions and questions[0]["qtype"] == "cloze"
    assert "____" in questions[0]["stem"]


def test_quiz_answer_records(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.set_setting(conn, "exam_date", "2026-09-13")
    today = date.today().isoformat()
    service.ensure_today_plan(conn, today)
    questions = quiz_service.build_daily_quiz(conn, today)
    quiz_service.record_quiz_answer(conn, questions[0]["id"], "随便答", False)
    stats = service.today_stats(conn, today)
    assert stats["quiz_total"] == 1 and stats["quiz_correct"] == 0
    assert stats["days_left"] == (date(2026, 9, 13) - date.today()).days


def test_settings_and_days_left(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    assert service.days_left(conn, "2026-08-27") is None
    service.set_setting(conn, "exam_date", "2026-09-13")
    assert service.days_left(conn, "2026-08-27") == 17


def test_morning_report_reuses_same_day(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    first = service.morning_report(conn, "2026-08-27")
    second = service.morning_report(conn, "2026-08-27")
    assert first["id"] == second["id"]
    assert "早上好" in first["content"] or first["content"]
    assert "新学 5" in first["content"]


def test_assistant_context_finds_entry(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    context, ids, refs = service.assistant_context(conn, "考点3")
    assert "XF-003" in ids
    assert "考点3" in context


def test_listen_queue_unheard_first_and_remaining(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.record_review(conn, "XF-001", "listen", "exposed", 30)
    data = service.listen_queue(conn)
    assert data["remaining"] == 4
    ids = [e["id"] for e in data["items"]]
    assert ids[0] == "XF-002"  # 未听优先
    assert "XF-001" in ids     # 已听排后面


def test_listen_queue_orders_by_priority_then_subject(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, n=3)
    # 追加一条普通优先级 + 一条理论法高频，验证排序权重
    extra = [{
        "id": "LL-001", "subject": "理论法", "submodule": "法理学",
        "point": "考点LL", "anchor": "乙实施行为后产生完整案件事实描述",
        "conclusion": "成立理论结论。", "priority": "高频考点",
        "rationale": "高频", "sources": [{"type": "高频", "ref": "x.md", "loc": "x"}],
        "statutes": [], "note": None, "tts_text": "【理论法】考点LL。",
    }, {
        "id": "XF-099", "subject": "刑法", "submodule": "分则",
        "point": "考点普通", "anchor": "丙实施行为后产生完整案件事实描述",
        "conclusion": "成立普通结论。", "priority": "普通",
        "rationale": "普通", "sources": [{"type": "高频", "ref": "x.md", "loc": "x"}],
        "statutes": [], "note": None, "tts_text": "【刑法】考点普通。",
    }]
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": 2, "entries": extra})
    data = service.listen_queue(conn)
    ids = [e["id"] for e in data["items"]]
    # 未听全部在前；未听内：高频（刑法 XF-001/2/3 → 理论法 LL-001）→ 普通 XF-099
    assert ids.index("LL-001") < ids.index("XF-099")
    assert ids.index("XF-001") < ids.index("LL-001")


def test_listen_queue_not_truncated_by_id_before_ranking(tmp_db):
    """id 字典序在前的科目（如 LL）不应挤掉未听高频的 XF 条目。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    entries = []
    for i in range(1, 101):
        entries.append({
            "id": f"LL-{i:03d}", "subject": "理论法", "submodule": "法理学",
            "point": f"理论点{i}", "anchor": f"甲实施行为{i}产生完整案件事实描述",
            "conclusion": f"成立理论结论{i}。", "priority": "普通",
            "rationale": "普通", "sources": [{"type": "高频", "ref": "x.md", "loc": "x"}],
            "statutes": [], "note": None, "tts_text": f"【理论法】点{i}。",
        })
    for i in range(1, 51):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "总则",
            "point": f"刑法点{i}", "anchor": f"乙实施行为{i}产生完整案件事实描述",
            "conclusion": f"成立刑法结论{i}。", "priority": "高频考点",
            "rationale": "高频", "sources": [{"type": "高频", "ref": "x.md", "loc": "x"}],
            "statutes": [], "note": None, "tts_text": f"【刑法】点{i}。",
        })
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": len(entries),
                                   "entries": entries})
    data = service.listen_queue(conn, limit=100)
    ids = [e["id"] for e in data["items"]]
    assert len(ids) == 100
    assert all(i.startswith("XF-") for i in ids[:10])  # 高频刑法未被 id 截断挤出


def test_ensure_listen_pool_triggers_when_low(tmp_db, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, n=3)
    from app import generator
    monkeypatch.setattr(generator, "ensure_generation", lambda c: True)
    assert service.ensure_listen_pool(conn, threshold=5) is True
    monkeypatch.setattr(generator, "ensure_generation", lambda c: False)
    assert service.ensure_listen_pool(conn, threshold=2) is False
