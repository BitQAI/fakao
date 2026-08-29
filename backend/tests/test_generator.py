from app import db
from app import generator


def _seed_subject(conn, subject, n):
    entries = [{
        "id": f"{generator.SUBJECT_PREFIX[subject]}-{i:03d}",
        "subject": subject, "submodule": "测试", "point": f"考点{i}",
        "anchor": f"甲实施行为{i}造成后果{i}案件事实完整描述",
        "conclusion": f"成立结论{i}。", "priority": "高频考点",
        "rationale": "测试", "sources": [{"type": "高频", "ref": "x.md", "loc": "x"}],
        "statutes": [], "note": None, "tts_text": f"【{subject}】考点{i}。",
    } for i in range(1, n + 1)]
    conn.executemany(
        "INSERT INTO entries (id, subject, submodule, point, anchor, conclusion,"
        " priority, rationale, sources, cases, statutes, note, tts_text, status)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(e["id"], e["subject"], e["submodule"], e["point"], e["anchor"],
          e["conclusion"], e["priority"], e["rationale"], "[]", "[]", "[]",
          None, e["tts_text"], "final") for e in entries],
    )
    conn.commit()


def test_next_pending_subject_order(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    assert generator.next_pending_subject(conn) == "民诉"
    _seed_subject(conn, "民诉", generator.SUBJECT_TARGET)
    assert generator.next_pending_subject(conn) == "商经知"


def test_next_pending_subject_none_when_full(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    for s in generator.SUBJECT_ORDER:
        _seed_subject(conn, s, generator.SUBJECT_TARGET)
    assert generator.next_pending_subject(conn) is None


def test_ensure_generation_no_reentrant(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    generator._running = True
    try:
        assert generator.ensure_generation(conn) is False
    finally:
        generator._running = False


def test_ensure_generation_starts_worker(tmp_db, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    generator._running = False
    started = {"n": 0}
    monkeypatch.setattr(generator.threading, "Thread",
                        lambda *a, **k: started.update(n=1) or _FakeThread())
    assert generator.ensure_generation(conn) is True
    assert started["n"] == 1
    generator._running = False


class _FakeThread:
    def start(self):
        return None
