import sqlite3

from app import db, quiz_bank


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


def test_case_questions_columns(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(case_questions)").fetchall()}
    assert {"qtype", "materials", "points", "reference"} <= cols
    conn.close()


def test_legacy_case_questions_gets_new_columns(tmp_db):
    """存量库缺 qtype/materials 时，connect 的幂等 ALTER 必须补齐且有默认值。"""
    db_path, _ = tmp_db
    raw = sqlite3.connect(db_path)
    raw.execute(
        "CREATE TABLE case_questions ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, case_source TEXT NOT NULL,"
        " case_loc TEXT NOT NULL, subject TEXT NOT NULL, stem TEXT NOT NULL,"
        " questions TEXT NOT NULL DEFAULT '[]', points TEXT NOT NULL DEFAULT '[]',"
        " reference TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft',"
        " created_at TEXT NOT NULL)")
    raw.execute("INSERT INTO case_questions (case_source, case_loc, subject, stem,"
                " created_at) VALUES ('s','l','民法','x','2026-01-01')")
    raw.commit()
    raw.close()

    conn = db.connect(db_path)
    row = conn.execute("SELECT qtype, materials FROM case_questions").fetchone()
    assert row["qtype"] == "case" and row["materials"] == "[]"
    conn.close()


def test_quiz_bank_columns_and_tts_assets(tmp_db):
    """新建库：quizzes 具备题库字段，judge 题型可用；tts_assets 台账表存在。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
    assert {"origin", "basis", "status", "text_hash"} <= cols
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "tts_assets" in tables
    conn.execute(
        "INSERT INTO entries (id, subject, submodule, point, anchor, conclusion, "
        "priority, rationale, sources, statutes, tts_text, status) "
        "VALUES ('XF-001','刑法','分则','考点','锚点句足够长用于校验','结论。',"
        "'高频考点','高频','[]','[]','【刑法·考点】结论。','final')"
    )
    conn.execute(
        "INSERT INTO quizzes (entry_id, qtype, origin, stem, options, answer,"
        " analysis, basis, status, text_hash, created_at) "
        "VALUES ('XF-001','judge','judge','刑事拘留最长37日。','[]','对','x','刑诉法91条',"
        "'published','h1','2026-09-20T10:00:00')"
    )
    conn.commit()
    conn.close()


def test_judge_capable_but_legacy_shape_migrates(tmp_db):
    """已含 judge 但 entry_id 仍 NOT NULL、缺 subject/point 的中间态也要能升级。"""
    db_path, _ = tmp_db
    raw = sqlite3.connect(db_path)
    raw.executescript(
        "CREATE TABLE quizzes ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " entry_id TEXT NOT NULL REFERENCES entries(id),"
        " qtype TEXT NOT NULL CHECK(qtype IN ('choice','cloze','judge')),"
        " origin TEXT NOT NULL DEFAULT 'daily',"
        " stem TEXT NOT NULL, options TEXT NOT NULL DEFAULT '[]',"
        " answer TEXT NOT NULL, analysis TEXT NOT NULL DEFAULT '',"
        " basis TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'published',"
        " text_hash TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);"
        "CREATE TABLE quiz_answers ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, quiz_id INTEGER NOT NULL,"
        " ts TEXT NOT NULL, user_answer TEXT NOT NULL, correct INTEGER NOT NULL,"
        " duration_sec INTEGER NOT NULL DEFAULT 0);"
    )
    raw.commit()
    raw.close()

    conn = db.connect(db_path)
    info = {r["name"]: r for r in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
    assert info["entry_id"]["notnull"] == 0
    assert {"subject", "point"} <= set(info)
    # entry_id 可空：法条派生的判断题无需挂条目
    conn.execute(
        "INSERT INTO quizzes (entry_id, subject, point, qtype, origin, stem, options,"
        " answer, analysis, basis, status, text_hash, created_at) "
        "VALUES (NULL,'刑诉','强制措施','judge','judge','刑事拘留最长37日。','[]','错',"
        "'最长37日为提请批准逮捕期限整体表述，须区分拘留期限。','刑诉法91条',"
        "'published','h3','2026-09-20T11:00:00')"
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM quizzes WHERE entry_id IS NULL"
                        ).fetchone()[0] == 1
    conn.close()


def test_quizzes_gains_variant_and_archived_status(tmp_db):
    """现网形态（含 judge、entry_id 可空）缺 variant/archived 时重建：
    依据 basis 必须保留，variant 回填 number，archived 不被批量发布复活。"""
    db_path, _ = tmp_db
    raw = sqlite3.connect(db_path)
    raw.executescript(
        "CREATE TABLE quizzes ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT REFERENCES entries(id),"
        " subject TEXT NOT NULL DEFAULT '', point TEXT NOT NULL DEFAULT '',"
        " qtype TEXT NOT NULL CHECK(qtype IN ('choice','cloze','judge')),"
        " origin TEXT NOT NULL DEFAULT 'daily'"
        "   CHECK(origin IN ('daily','bank','judge')),"
        " stem TEXT NOT NULL, options TEXT NOT NULL DEFAULT '[]',"
        " answer TEXT NOT NULL, analysis TEXT NOT NULL DEFAULT '',"
        " basis TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'published'"
        "   CHECK(status IN ('draft','published')),"
        " text_hash TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);"
        "CREATE TABLE quiz_answers ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, quiz_id INTEGER NOT NULL,"
        " ts TEXT NOT NULL, user_answer TEXT NOT NULL, correct INTEGER NOT NULL,"
        " duration_sec INTEGER NOT NULL DEFAULT 0);"
        "INSERT INTO quizzes (entry_id, subject, point, qtype, origin, stem, options,"
        " answer, analysis, basis, status, text_hash, created_at) "
        "VALUES (NULL,'刑诉','强制措施','judge','judge','刑事拘留最长37日。','[]','对',"
        "'拘留期限。','刑诉法第91条','draft','h1','2026-09-20T10:00:00');"
    )
    raw.commit()
    raw.close()

    conn = db.connect(db_path)
    info = {r["name"] for r in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
    assert "variant" in info
    row = conn.execute("SELECT * FROM quizzes WHERE id=1").fetchone()
    assert row["basis"] == "刑诉法第91条"      # 重建不得丢掉依据
    assert row["variant"] == "number"          # 历史判断题回填数字型
    conn.execute("UPDATE quizzes SET status='archived' WHERE id=1")
    conn.commit()
    quiz_bank.set_status(conn, origins=("judge",), status="published")
    assert conn.execute("SELECT status FROM quizzes WHERE id=1").fetchone()[0] == "archived"
    conn.close()


def test_legacy_quizzes_table_migrates_to_judge_schema(tmp_db):
    """存量库旧 CHECK('choice','cloze') 必须重建为含 judge，且数据不丢。"""
    db_path, _ = tmp_db
    raw = sqlite3.connect(db_path)
    raw.executescript(
        "CREATE TABLE quizzes ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL,"
        " qtype TEXT NOT NULL CHECK(qtype IN ('choice','cloze')), stem TEXT NOT NULL,"
        " options TEXT NOT NULL DEFAULT '[]', answer TEXT NOT NULL,"
        " analysis TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);"
        "CREATE TABLE quiz_answers ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, quiz_id INTEGER NOT NULL,"
        " ts TEXT NOT NULL, user_answer TEXT NOT NULL, correct INTEGER NOT NULL,"
        " duration_sec INTEGER NOT NULL DEFAULT 0);"
        "INSERT INTO quizzes (entry_id, qtype, stem, options, answer, analysis,"
        " created_at) VALUES ('XF-001','choice','旧题','[\"A. x\"]','A','旧解析',"
        "'2026-09-01T09:00:00');"
        "INSERT INTO quiz_answers (quiz_id, ts, user_answer, correct, duration_sec)"
        " VALUES (1,'2026-09-01T09:05:00','A',1,12);"
    )
    raw.commit()
    raw.close()

    conn = db.connect(db_path)
    row = conn.execute("SELECT * FROM quizzes WHERE id=1").fetchone()
    assert row["stem"] == "旧题" and row["analysis"] == "旧解析"
    assert row["origin"] == "daily" and row["status"] == "published"
    assert row["text_hash"]
    ans = conn.execute("SELECT * FROM quiz_answers WHERE id=1").fetchone()
    assert ans["quiz_id"] == 1 and ans["duration_sec"] == 12
    conn.execute(
        "INSERT INTO entries (id, subject, submodule, point, anchor, conclusion, "
        "priority, rationale, sources, statutes, tts_text, status) "
        "VALUES ('XF-001','刑法','分则','考点','锚点句足够长用于校验','结论。',"
        "'高频考点','高频','[]','[]','【刑法·考点】结论。','final')"
    )
    # 重建后 judge 题型可写入
    conn.execute(
        "INSERT INTO quizzes (entry_id, qtype, origin, stem, options, answer,"
        " analysis, basis, status, text_hash, created_at) "
        "VALUES ('XF-001','judge','judge','判断句','[]','错','解析','刑法第5条',"
        "'published','h2','2026-09-20T10:00:00')"
    )
    conn.commit()
    conn.close()
