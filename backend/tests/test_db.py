import sqlite3

from app import db


def test_connect_creates_tables(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"entries", "reviews", "quizzes", "quiz_answers",
            "daily_plans", "reports", "chat_logs", "cases", "settings"} <= names


def test_connect_sets_row_factory(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    assert conn.row_factory is sqlite3.Row


def test_entries_columns(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(entries)").fetchall()]
    assert {"id", "cases", "tts_text", "status"} <= set(cols)
    assert "tags" not in cols


def test_reviews_check_constraint(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    conn.execute(
        "INSERT INTO entries (id, subject, submodule, point, anchor, conclusion, "
        "priority, rationale, sources, statutes, tts_text, status) "
        "VALUES ('XF-001','刑法','分则-财产犯罪','转化型抢劫','甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤',"
        "'成立抢劫罪。','高频考点','高频','[]','[\"刑法269条\"]','【刑法·转化型抢劫】……','final')"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO reviews (entry_id, ts, mode, result, duration_sec) "
            "VALUES ('XF-001','2026-08-27T08:00:00','read','nonsense',5)"
        )
        conn.commit()
        assert False, "非法 result 应被 CHECK 约束拒绝"
    except sqlite3.IntegrityError:
        pass
