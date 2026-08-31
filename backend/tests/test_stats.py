from datetime import date, timedelta

import pytest

from app import ai
from app import db, importer, service, stats


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)


def seed(conn, n=3):
    entries = []
    for i in range(1, n + 1):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "分则",
            "point": f"考点{i}", "anchor": f"甲实施行为{i}，造成后果{i}，案件事实完整描述",
            "conclusion": f"成立罪名{i}。", "priority": "高频考点",
            "rationale": "高频",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md", "loc": "x"}],
            "statutes": [], "note": None, "tts_text": f"结论{i}。"})
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": n, "entries": entries})


def _review(conn, entry_id, ts, mode="read", result="good"):
    conn.execute(
        "INSERT INTO reviews (entry_id, ts, mode, result, duration_sec) "
        "VALUES (?,?,?,?,?)", (entry_id, ts, mode, result, 0))
    conn.commit()


def test_streak_info_current_and_longest(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    today = date.today()
    # 今天、昨天、前天连续；再往前断档；更早 3 天连续
    for i in (0, 1, 2):
        _review(conn, "XF-001", (today - timedelta(days=i)).isoformat() + "T10:00:00")
    for i in (5, 6, 7):
        _review(conn, "XF-002", (today - timedelta(days=i)).isoformat() + "T10:00:00")
    info = stats.streak_info(conn, today.isoformat())
    assert info["current"] == 3
    assert info["longest"] == 3


def test_overview_zero_fill_totals_mastery(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    today = date.today()
    _review(conn, "XF-001", today.isoformat() + "T10:00:00")
    _review(conn, "XF-001", today.isoformat() + "T11:00:00", mode="listen")
    _review(conn, "XF-002", (today - timedelta(days=1)).isoformat() + "T10:00:00")
    # 错题 → weak
    _review(conn, "XF-003", (today - timedelta(days=2)).isoformat() + "T10:00:00",
            result="bad")
    data = stats.overview(conn, days=30)
    assert data["days"] == 30
    assert len(data["daily"]) == 30
    assert data["daily"][-1]["read"] == 1
    assert data["daily"][-1]["listen"] == 1
    assert data["totals"]["read"] == 3
    assert data["totals"]["listen"] == 1
    assert data["totals"]["quiz"] == 0
    assert data["streak"]["current"] >= 1
    assert data["mastery"]["weak"] == 1
    assert data["mastery"]["learned"] == 2
    assert data["mastery"]["new"] == 0


def test_overview_days_capped(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    assert stats.overview(conn, days=999)["days"] == 180
