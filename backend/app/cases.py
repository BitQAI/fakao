"""案例库统一文档装载与查询（数据底座：Task 0 产出 JSONL → SQLite cases 表）。"""
import json
from pathlib import Path

from app import config

CASE_SOURCES = ("人民法院案例库", "司法部案例库", "最高检指导性案例", "最高法指导性案例")


def _records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ensure_cases_loaded(conn, docs_dir: Path | None = None) -> dict:
    """JSONL 全文入库（幂等：cases 表行数等于 JSONL 行数则跳过）。"""
    docs_dir = Path(docs_dir) if docs_dir else config.CASES_DOCS_DIR
    total = 0
    for source in CASE_SOURCES:
        path = docs_dir / f"{source}.jsonl"
        records = _records(path)
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM cases WHERE source=?", (source,)
        ).fetchone()["n"]
        if count == len(records):
            total += count
            continue
        conn.execute("DELETE FROM cases WHERE source=?", (source,))
        conn.executemany(
            "INSERT OR REPLACE INTO cases "
            "(source, loc, title, category, case_no, keywords, date, url, text) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(r["source"], r["id"], r["title"], r["category"], r["case_no"],
              json.dumps(r["keywords"], ensure_ascii=False), r["date"],
              r["url"], r["text"]) for r in records],
        )
        total += len(records)
    conn.commit()
    return {"loaded": total}


def get_case(conn, source: str, loc: str) -> dict | None:
    row = conn.execute(
        "SELECT source, loc, title, category, case_no, keywords, date, url, text "
        "FROM cases WHERE source=? AND loc=?", (source, loc)
    ).fetchone()
    if row is None and config.CASES_DOCS_DIR.exists():
        # 文档存在但案例未装载（本地/新库开箱即用）：幂等装载后重查
        ensure_cases_loaded(conn)
        row = conn.execute(
            "SELECT source, loc, title, category, case_no, keywords, date, url, text "
            "FROM cases WHERE source=? AND loc=?", (source, loc)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["keywords"] = json.loads(d["keywords"] or "[]")
    return d
