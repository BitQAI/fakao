from datetime import date

import pytest

from app import ai
from app import db, importer, quiz_service, service, stats


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """错题本测试不访问真实 DeepSeek（.env 有 key，避免真实计费/波动）。"""
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)


def seed(conn, n=5):
    entries = []
    for i in range(1, n + 1):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": f"考点{i}", "anchor": f"甲实施行为{i}，造成后果{i}，案件事实完整描述",
            "conclusion": f"成立罪名{i}。", "priority": "高频考点",
            "rationale": "高频",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md", "loc": "x"}],
            "statutes": [], "note": None, "tts_text": f"结论{i}。"})
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": n, "entries": entries})


def test_wrongbook_aggregates_quiz_and_bad(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    today = date.today().isoformat()
    service.ensure_today_plan(conn, today)
    questions = quiz_service.build_daily_quiz(conn, today)
    # 考点1：quiz 错 1 次（ts=now）+ 看背 bad 1 次
    quiz_service.record_quiz_answer(conn, questions[0]["id"], "错", False)
    # 考点1/2 的 bad 用受控时间戳：考点2 的 bad 更早 → 考点1 因 quiz 错排在更前
    for eid, ts in (("XF-001", "2026-08-30T10:00:00"),
                    ("XF-002", "2026-08-30T09:30:00")):
        conn.execute(
            "INSERT INTO reviews (entry_id, ts, mode, result, duration_sec) "
            "VALUES (?,?,?,?,?)", (eid, ts, "read", "bad", 0))
    conn.commit()
    # 考点3：正常 good，不进错题本
    service.record_review(conn, "XF-003", "read", "good")
    items = stats.wrongbook(conn)
    by_id = {it["id"]: it for it in items}
    assert by_id["XF-001"]["wrong_count"] == 2
    assert by_id["XF-001"]["quiz_wrong_count"] == 1
    assert by_id["XF-001"]["bad_count"] == 1
    assert by_id["XF-002"]["wrong_count"] == 1
    assert "XF-003" not in by_id
    # 最近错误优先：考点1 最后错误（quiz now）晚于考点2
    assert items[0]["id"] == "XF-001"


def test_wrongbook_queue_returns_full_entries(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.record_review(conn, "XF-001", "read", "bad")
    service.record_review(conn, "XF-002", "read", "bad")
    items = stats.wrongbook_queue(conn, limit=30)
    assert [it["id"] for it in items] == ["XF-001", "XF-002"]
    assert "conclusion" in items[0]
    assert "tts_text" in items[0]


def test_wrongbook_empty(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.record_review(conn, "XF-001", "read", "good")
    assert stats.wrongbook(conn) == []
    assert stats.wrongbook_queue(conn) == []
