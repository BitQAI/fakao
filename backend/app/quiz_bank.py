"""题库：入库、抽题、状态流转。

题库题与「当日缓存题」同表（quizzes），用 origin 区分：
- daily：按天懒生成的缓存题（用户点开时生成，当天复用）
- bank ：客观题题库（由条目派生，离线批量生成）
- judge：数字判断题题库（由法条数字条文 / 条目数字结论派生）

判分仍走 quiz_answers，错题本、做题历史、复盘统计无需改动。
"""
import json
from datetime import datetime

from app import db

ORIGIN_BANK = "bank"
ORIGIN_JUDGE = "judge"

_JUDGE_TRUE = {"对", "正确", "是", "true", "t", "y", "yes", "1"}
_JUDGE_FALSE = {"错", "错误", "否", "false", "f", "n", "no", "0"}

_SELECT_COLS = ("id, entry_id, subject, point, qtype, stem, options, answer,"
                " analysis, basis")


def normalize_judge_answer(value: str) -> str | None:
    """把「对/错/正确/T/F…」归一为「对」或「错」；无法识别返回 None。"""
    text = (value or "").strip().lower()
    if text in _JUDGE_TRUE:
        return "对"
    if text in _JUDGE_FALSE:
        return "错"
    return None


def _row_to_question(row) -> dict:
    return {
        "id": row["id"], "entry_id": row["entry_id"], "subject": row["subject"],
        "point": row["point"], "qtype": row["qtype"], "stem": row["stem"],
        "options": json.loads(row["options"] or "[]"), "answer": row["answer"],
        "analysis": row["analysis"] or "", "basis": row["basis"] or "",
    }


def find_question(conn, *, origin: str, qtype: str, entry_id: str | None,
                  text_hash: str) -> dict | None:
    """按 (origin, entry_id, qtype) 或 (origin, qtype, text_hash) 查同题。"""
    if entry_id:
        row = conn.execute(
            "SELECT id, text_hash FROM quizzes WHERE origin=? AND qtype=? AND entry_id=?"
            " ORDER BY id LIMIT 1", (origin, qtype, entry_id)).fetchone()
    else:
        row = conn.execute(
            "SELECT id, text_hash FROM quizzes WHERE origin=? AND qtype=? AND text_hash=?"
            " ORDER BY id LIMIT 1", (origin, qtype, text_hash)).fetchone()
    return dict(row) if row else None


def save_question(conn, *, qtype: str, origin: str, stem: str, answer: str,
                  analysis: str = "", basis: str = "", entry_id: str | None = None,
                  subject: str = "", point: str = "", options: list[str] | None = None,
                  status: str = "draft", replace: bool = False) -> int | None:
    """写入一道题库题（幂等）。

    - 同 key 已存在且指纹相同：直接返回原 id（不重复出题、不重复计费）
    - 同 key 已存在但指纹不同：`replace=True` 时覆盖，否则保留原题
    """
    options = options or []
    text_hash = db.question_hash(stem, answer, options)
    existing = find_question(conn, origin=origin, qtype=qtype, entry_id=entry_id,
                             text_hash=text_hash)
    if existing is not None:
        if existing["text_hash"] == text_hash or not replace:
            return existing["id"]
        conn.execute(
            "UPDATE quizzes SET stem=?, options=?, answer=?, analysis=?, basis=?,"
            " subject=?, point=?, status=?, text_hash=? WHERE id=?",
            (stem, json.dumps(options, ensure_ascii=False), answer, analysis, basis,
             subject, point, status, text_hash, existing["id"]))
        conn.commit()
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO quizzes (entry_id, subject, point, qtype, origin, stem, options,"
        " answer, analysis, basis, status, text_hash, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry_id, subject, point, qtype, origin, stem,
         json.dumps(options, ensure_ascii=False), answer, analysis, basis, status,
         text_hash, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return cur.lastrowid


def pick(conn, *, origins: tuple[str, ...] = (ORIGIN_BANK,), limit: int = 10,
         subjects: list[str] | None = None, points: list[str] | None = None,
         qtypes: list[str] | None = None, status: str = "published") -> list[dict]:
    """按科目/知识点随机抽题。"""
    where = ["origin IN (%s)" % ",".join("?" * len(origins)), "status=?"]
    params: list = [*origins, status]
    for column, values in (("qtype", qtypes), ("subject", subjects), ("point", points)):
        if values:
            where.append("%s IN (%s)" % (column, ",".join("?" * len(values))))
            params += list(values)
    params.append(max(1, int(limit)))
    rows = conn.execute(
        f"SELECT {_SELECT_COLS} FROM quizzes WHERE {' AND '.join(where)}"
        " ORDER BY RANDOM() LIMIT ?", params).fetchall()
    return [_row_to_question(r) for r in rows]


def set_status(conn, *, origins: tuple[str, ...], status: str,
               subjects: list[str] | None = None) -> int:
    """批量转状态（draft → published 发布 / 回退），返回影响行数。"""
    sql = ("UPDATE quizzes SET status=? WHERE origin IN (%s)"
           % ",".join("?" * len(origins)))
    params: list = [status, *origins]
    if subjects:
        sql += " AND subject IN (%s)" % ",".join("?" * len(subjects))
        params += list(subjects)
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount


def stats(conn) -> list[dict]:
    """题库概览：按 origin / qtype / status 计数（不含当日缓存题）。"""
    return [dict(r) for r in conn.execute(
        "SELECT origin, qtype, status, COUNT(*) AS n FROM quizzes"
        " WHERE origin != 'daily' GROUP BY origin, qtype, status"
        " ORDER BY origin, qtype, status").fetchall()]


def question_for_entry(conn, entry_id: str,
                       origins: tuple[str, ...] = (ORIGIN_BANK,
                                                   ORIGIN_JUDGE)) -> dict | None:
    """取某条目的已发布题库题（客观题优先，其次判断题）。"""
    row = conn.execute(
        f"SELECT {_SELECT_COLS} FROM quizzes WHERE entry_id=? AND status='published'"
        " AND origin IN (%s) ORDER BY CASE qtype WHEN 'choice' THEN 0 ELSE 1 END, id"
        " LIMIT 1" % ",".join("?" * len(origins)),
        (entry_id, *origins)).fetchone()
    return _row_to_question(row) if row else None
