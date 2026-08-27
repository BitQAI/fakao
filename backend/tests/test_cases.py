import json

from app import cases, db


def _seed_jsonl(tmp_path):
    docs = tmp_path / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "人民法院案例库.jsonl").write_text(json.dumps({
        "id": "case_00001", "source": "人民法院案例库", "title": "甲诉乙案",
        "category": "参考案例", "case_no": "（2026）苏01民终1号",
        "keywords": ["民事"], "date": "2026-01-01", "url": "", "text": "案情正文",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    return docs


def test_ensure_cases_loaded(tmp_db, tmp_path):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    docs = _seed_jsonl(tmp_path)
    assert cases.ensure_cases_loaded(conn, docs) == {"loaded": 1}
    assert conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"] == 1


def test_ensure_cases_idempotent(tmp_db, tmp_path):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    cases.ensure_cases_loaded(conn, _seed_jsonl(tmp_path))
    assert cases.ensure_cases_loaded(conn, _seed_jsonl(tmp_path)) == {"loaded": 1}
    assert conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"] == 1


def test_get_case(tmp_db, tmp_path):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    cases.ensure_cases_loaded(conn, _seed_jsonl(tmp_path))
    rec = cases.get_case(conn, "人民法院案例库", "case_00001")
    assert rec is not None and rec["title"] == "甲诉乙案" and rec["keywords"] == ["民事"]
    assert cases.get_case(conn, "人民法院案例库", "nope") is None
