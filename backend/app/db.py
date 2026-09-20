"""SQLite 连接与全部表结构。"""
import json
import sqlite3
from datetime import datetime
from hashlib import sha1
from pathlib import Path

from app import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
  id         TEXT PRIMARY KEY,
  subject    TEXT NOT NULL,
  submodule  TEXT NOT NULL,
  point      TEXT NOT NULL,
  anchor     TEXT NOT NULL,
  conclusion TEXT NOT NULL,
  priority   TEXT NOT NULL CHECK(priority IN ('高频考点','易错陷阱','新增必考','普通')),
  rationale  TEXT NOT NULL,
  sources    TEXT NOT NULL DEFAULT '[]',
  cases      TEXT NOT NULL DEFAULT '[]',
  statutes   TEXT NOT NULL DEFAULT '[]',
  note       TEXT,
  tts_text   TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS reviews (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id     TEXT NOT NULL REFERENCES entries(id),
  ts           TEXT NOT NULL,
  mode         TEXT NOT NULL CHECK(mode IN ('read','listen','quiz')),
  result       TEXT NOT NULL CHECK(result IN ('good','fuzzy','bad','exposed')),
  duration_sec INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reviews_entry ON reviews(entry_id, ts);

-- origin：daily=当日缓存题（按天生成）/ bank=客观题库 / judge=数字判断题题库
-- status：题库题先入库为 draft，抽检后 --publish 转 published（当日缓存题直接 published）
-- entry_id 可空：法条派生的判断题不挂条目；subject/point 冗余存储，供按科目知识点抽题
CREATE TABLE IF NOT EXISTS quizzes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id   TEXT REFERENCES entries(id),
  subject    TEXT NOT NULL DEFAULT '',
  point      TEXT NOT NULL DEFAULT '',
  qtype      TEXT NOT NULL CHECK(qtype IN ('choice','cloze','judge')),
  origin     TEXT NOT NULL DEFAULT 'daily' CHECK(origin IN ('daily','bank','judge')),
  stem       TEXT NOT NULL,
  options    TEXT NOT NULL DEFAULT '[]',
  answer     TEXT NOT NULL,
  analysis   TEXT NOT NULL DEFAULT '',
  basis      TEXT NOT NULL DEFAULT '',
  status     TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('draft','published')),
  text_hash  TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_answers (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  quiz_id      INTEGER NOT NULL REFERENCES quizzes(id),
  ts           TEXT NOT NULL,
  user_answer  TEXT NOT NULL,
  correct      INTEGER NOT NULL,
  duration_sec INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_plans (
  date      TEXT PRIMARY KEY,
  items     TEXT NOT NULL DEFAULT '[]',
  quota     INTEGER NOT NULL,
  rationale TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS reports (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  date       TEXT NOT NULL,
  kind       TEXT NOT NULL CHECK(kind IN ('morning','evening')),
  content    TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_logs (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                TEXT NOT NULL,
  question          TEXT NOT NULL,
  answer            TEXT NOT NULL,
  related_entry_ids TEXT NOT NULL DEFAULT '[]',
  source_refs       TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS cases (
  source   TEXT NOT NULL,
  loc      TEXT NOT NULL,
  title    TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  case_no  TEXT NOT NULL DEFAULT '',
  keywords TEXT NOT NULL DEFAULT '[]',
  date     TEXT NOT NULL DEFAULT '',
  url      TEXT NOT NULL DEFAULT '',
  text     TEXT NOT NULL,
  PRIMARY KEY (source, loc)
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id   TEXT NOT NULL REFERENCES entries(id),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marks_entry ON marks(entry_id, created_at);

-- 每日案例（微主观题）：题干 + 设问 + 采分点，由 scripts/build_case_questions.py 生成
CREATE TABLE IF NOT EXISTS case_questions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  case_source TEXT NOT NULL,
  case_loc    TEXT NOT NULL,
  subject     TEXT NOT NULL,
  qtype       TEXT NOT NULL DEFAULT 'case'
              CHECK(qtype IN ('case','essay','composite')),
  stem        TEXT NOT NULL,
  questions   TEXT NOT NULL DEFAULT '[]',
  points      TEXT NOT NULL DEFAULT '[]',
  materials   TEXT NOT NULL DEFAULT '[]',
  reference   TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'draft'
              CHECK(status IN ('draft','published')),
  created_at  TEXT NOT NULL,
  UNIQUE(case_source, case_loc)
);
CREATE INDEX IF NOT EXISTS idx_case_questions_status
  ON case_questions(status, subject, id);

CREATE TABLE IF NOT EXISTS case_attempts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id  INTEGER NOT NULL REFERENCES case_questions(id),
  ts           TEXT NOT NULL,
  mode         TEXT NOT NULL CHECK(mode IN ('write','listen')),
  answer_text  TEXT,
  hit_points   TEXT NOT NULL DEFAULT '[]',
  score        INTEGER NOT NULL DEFAULT 0,
  duration_sec INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_case_attempts_q ON case_attempts(question_id, ts);

-- 听学音频台账：支撑「文本变了→音频陈旧」检测与幂等重合成
CREATE TABLE IF NOT EXISTS tts_assets (
  entry_id     TEXT PRIMARY KEY,
  text_hash    TEXT NOT NULL,
  speed        REAL NOT NULL DEFAULT 1.0,
  bytes        INTEGER NOT NULL DEFAULT 0,
  duration_sec REAL NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);
"""

# 题库表重建语句（旧库 qtype CHECK 不含 judge，SQLite 无法直接改 CHECK）
_QUIZ_TABLE_SQL = """
CREATE TABLE quizzes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id   TEXT REFERENCES entries(id),
  subject    TEXT NOT NULL DEFAULT '',
  point      TEXT NOT NULL DEFAULT '',
  qtype      TEXT NOT NULL CHECK(qtype IN ('choice','cloze','judge')),
  origin     TEXT NOT NULL DEFAULT 'daily' CHECK(origin IN ('daily','bank','judge')),
  stem       TEXT NOT NULL,
  options    TEXT NOT NULL DEFAULT '[]',
  answer     TEXT NOT NULL,
  analysis   TEXT NOT NULL DEFAULT '',
  basis      TEXT NOT NULL DEFAULT '',
  status     TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('draft','published')),
  text_hash  TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
)
"""

_QUIZ_ANSWER_TABLE_SQL = """
CREATE TABLE quiz_answers (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  quiz_id      INTEGER NOT NULL REFERENCES quizzes(id),
  ts           TEXT NOT NULL,
  user_answer  TEXT NOT NULL,
  correct      INTEGER NOT NULL,
  duration_sec INTEGER NOT NULL DEFAULT 0
)
"""


def question_hash(stem: str, answer: str, options: list[str] | None = None) -> str:
    """题干+答案（+选项）指纹：题库幂等与音频陈旧检测共用。"""
    payload = "\x1f".join([stem or "", answer or "", *[o or "" for o in (options or [])]])
    return sha1(payload.encode("utf-8")).hexdigest()[:16]


def _backup_quiz_tables(conn) -> Path | None:
    """重建前把 quizzes/quiz_answers 全量导出 JSON（可回溯），失败不影响主流程。"""
    try:
        backup_dir = config.DATA_DIR / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = backup_dir / f"quizzes-{stamp}.json"
        payload = {
            "quizzes": [dict(r) for r in conn.execute("SELECT * FROM quizzes")],
            "quiz_answers": [dict(r) for r in conn.execute("SELECT * FROM quiz_answers")],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception:  # noqa: BLE001 - 备份失败不阻断迁移
        return None


def _quiz_rebuild_needed(conn) -> bool:
    """重建条件：qtype CHECK 不含 judge，或 entry_id 仍为 NOT NULL（题库需可空）。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='quizzes'"
    ).fetchone()
    if row is None:
        return False
    if "'judge'" not in (row["sql"] or ""):
        return True
    info = {r["name"]: r for r in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
    if "subject" not in info or "point" not in info:
        return True
    return bool(info["entry_id"]["notnull"])


def _migrate_quiz_schema(conn) -> None:
    """旧库 quizzes 结构升级：备份 → 重建两表 → 回填数据（含派生 subject/point）。"""
    if not _quiz_rebuild_needed(conn):
        return
    _backup_quiz_tables(conn)
    quizzes = [dict(r) for r in conn.execute("SELECT * FROM quizzes")]
    answers = [dict(r) for r in conn.execute("SELECT * FROM quiz_answers")]
    meta = {
        r["id"]: (r["subject"], r["point"])
        for r in conn.execute("SELECT id, subject, point FROM entries").fetchall()
    }
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("DROP TABLE IF EXISTS quiz_answers")
        conn.execute("DROP TABLE IF EXISTS quizzes")
        conn.execute(_QUIZ_TABLE_SQL)
        conn.execute(_QUIZ_ANSWER_TABLE_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_quizzes_origin "
            "ON quizzes(origin, status, subject)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_quizzes_entry ON quizzes(entry_id)")
        conn.executemany(
            "INSERT INTO quizzes (id, entry_id, subject, point, qtype, origin, stem,"
            " options, answer, analysis, basis, status, text_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(q["id"], q["entry_id"],
              q.get("subject") or meta.get(q["entry_id"], ("", ""))[0],
              q.get("point") or meta.get(q["entry_id"], ("", ""))[1],
              q["qtype"], q.get("origin") or "daily", q["stem"],
              q["options"] or "[]", q["answer"], q.get("analysis") or "", "",
              q.get("status") or "published", q.get("text_hash")
              or question_hash(q["stem"], q["answer"]), q["created_at"])
             for q in quizzes],
        )
        conn.executemany(
            "INSERT INTO quiz_answers (id, quiz_id, ts, user_answer, correct,"
            " duration_sec) VALUES (?,?,?,?,?,?)",
            [(a["id"], a["quiz_id"], a["ts"], a["user_answer"], a["correct"],
              a.get("duration_sec") or 0) for a in answers],
        )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：SSE 流式响应（assistant）在事件循环线程写聊天日志，
    # 同一请求的连接需跨线程复用（每请求独立连接，无并发共享）。
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    # 轻量迁移（本仓库无 Alembic，用幂等 ALTER / 重建）：
    # 1) 极旧库补齐 quizzes.analysis 列
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
    if "analysis" not in cols:
        conn.execute("ALTER TABLE quizzes ADD COLUMN analysis TEXT NOT NULL DEFAULT ''")
        cols.add("analysis")
    # 2) 存量库补齐题库列（qtype CHECK 需重建表，见 _migrate_quiz_schema）
    for col, ddl in (("origin", "TEXT NOT NULL DEFAULT 'daily'"),
                     ("basis", "TEXT NOT NULL DEFAULT ''"),
                     ("status", "TEXT NOT NULL DEFAULT 'published'"),
                     ("text_hash", "TEXT NOT NULL DEFAULT ''"),
                     ("subject", "TEXT NOT NULL DEFAULT ''"),
                     ("point", "TEXT NOT NULL DEFAULT ''")):
        if col not in cols:
            conn.execute(f"ALTER TABLE quizzes ADD COLUMN {col} {ddl}")
    conn.commit()
    _migrate_quiz_schema(conn)
    # 3) 题库索引：等 quizzes 结构确定后再建（旧库缺列时此处才会成功）
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quizzes_origin "
                 "ON quizzes(origin, status, subject)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quizzes_entry ON quizzes(entry_id)")
    # 4) 音频台账补齐 speed 列（早期建表无该列）
    tts_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tts_assets)")}
    if tts_cols and "speed" not in tts_cols:
        conn.execute("ALTER TABLE tts_assets ADD COLUMN speed REAL NOT NULL DEFAULT 1.0")
    conn.commit()
    # 存量库补齐 case_questions.qtype / materials（论述题与综合大案例复用同一张表）
    cq_cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(case_questions)").fetchall()}
    if cq_cols and "qtype" not in cq_cols:
        conn.execute("ALTER TABLE case_questions ADD COLUMN qtype TEXT "
                     "NOT NULL DEFAULT 'case'")
    if cq_cols and "materials" not in cq_cols:
        conn.execute("ALTER TABLE case_questions ADD COLUMN materials TEXT "
                     "NOT NULL DEFAULT '[]'")
    conn.commit()
    return conn


def get_db():
    """FastAPI 依赖：每请求一个连接，请求结束关闭。"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
