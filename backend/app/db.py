"""SQLite 连接与全部表结构。"""
import sqlite3
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

CREATE TABLE IF NOT EXISTS quizzes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id   TEXT NOT NULL REFERENCES entries(id),
  qtype      TEXT NOT NULL CHECK(qtype IN ('choice','cloze')),
  stem       TEXT NOT NULL,
  options    TEXT NOT NULL DEFAULT '[]',
  answer     TEXT NOT NULL,
  analysis   TEXT NOT NULL DEFAULT '',
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
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False：SSE 流式响应（assistant）在事件循环线程写聊天日志，
    # 同一请求的连接需跨线程复用（每请求独立连接，无并发共享）。
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    # 轻量迁移：存量库补齐 quizzes.analysis 列（本仓库无 Alembic，用幂等 ALTER）
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
    if "analysis" not in cols:
        conn.execute("ALTER TABLE quizzes ADD COLUMN analysis TEXT NOT NULL DEFAULT ''")
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
