"""法条卡：以「一条法条 + 基于它命制的题」为单位的练习素材。

自测、看背、听学、法条页四个入口共用这一份池子，保证法条驱动题在任一入口都能被穷尽
（此前它们只能在「组卷」里遇到）。数据只读 `quizzes` + `statute_index`，不新增业务表；
「看过/听过」记在轻量表 `card_seen`，避免给 `reviews`（entry_id 非空外键）加负担。
"""
import json
from datetime import datetime

from app import config, quiz_bank, statute_index, statutes

#: 卡片正文摘要长度上限（听学朗读与卡片背面共用，超长条文截断）
ARTICLE_SNIPPET = 160

#: read=看背，listen=听学，quiz=自测（作答后标记，用于轮转优先未练过的题）
MODES = ("read", "listen", "quiz")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS card_seen (
  card_key TEXT NOT NULL,
  mode     TEXT NOT NULL,
  ts       TEXT NOT NULL,
  PRIMARY KEY (card_key, mode)
)
"""


def ensure_table(conn) -> None:
    """幂等建表（看背/听学的「已看/已听」标记）。"""
    conn.execute(_SCHEMA)
    conn.commit()


def card_key(quiz_id: int) -> str:
    return f"q:{quiz_id}"


def mark_seen(conn, quiz_id: int, mode: str) -> None:
    ensure_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO card_seen (card_key, mode, ts) VALUES (?,?,?)",
        (card_key(quiz_id), mode,
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def seen_keys(conn, mode: str) -> set[int]:
    ensure_table(conn)
    return {int(r["card_key"][2:]) for r in conn.execute(
        "SELECT card_key FROM card_seen WHERE mode=?", (mode,))
        if r["card_key"].startswith("q:")}


def _placeholders(values) -> str:
    return ",".join("?" * len(values))


def _article_of(basis: str, library: dict):
    located = statutes.resolve_law_article(basis)
    if located is None:
        return None, 0, 0, None
    law_key, no, sub = located
    law = library.get(law_key)
    return law_key, no, sub, (law.article(no, sub) if law else None)


def _to_card(row, library: dict) -> dict:
    law_key, no, sub, article = _article_of(row["basis"], library)
    return {
        "kind": "statute",
        "quiz_id": row["id"],
        "card_key": card_key(row["id"]),
        "subject": row["subject"],
        "qtype": row["qtype"],
        "stem": row["stem"],
        "options": json.loads(row["options"] or "[]"),
        "answer": row["answer"],
        "analysis": row["analysis"] or "",
        "basis": row["basis"],
        "law_key": law_key or "",
        "no": no,
        "sub": sub,
        "article_text": article.text if article else "",
    }


_COLS = "id, subject, qtype, stem, options, answer, analysis, basis"
_FILTER = ("origin IN (?,?) AND status='published' AND entry_id IS NULL"
           " AND basis != ''")


def snippet(text: str, limit: int = ARTICLE_SNIPPET) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "……"


def pool(conn, *, subjects: list[str] | None = None, mode: str = "read",
         limit: int = 10, unseen_only: bool = False) -> list[dict]:
    """法条卡池：未看过/未听过的排前面，`subjects` 只是**偏好**（不排除其他科目），
    这样今日科目优先的同时，任何一天都能逐步覆盖到全部法条题。"""
    ensure_table(conn)
    where = [_FILTER]
    # 参数按 SQL 文本中 `?` 出现的顺序绑定：LEFT JOIN 的 mode 在最前
    params: list = [mode, quiz_bank.ORIGIN_BANK, quiz_bank.ORIGIN_JUDGE]
    if unseen_only:
        where.append("cs.card_key IS NULL")
    order = ["unseen DESC"]
    if subjects:
        order.append(f"(q.subject IN ({_placeholders(subjects)})) DESC")
        params += list(subjects)
    order.append("q.id")
    sql = (
        "SELECT q.id, q.subject, q.qtype, q.stem, q.options, q.answer, q.analysis,"
        " q.basis, (cs.card_key IS NULL) AS unseen FROM quizzes q"
        " LEFT JOIN card_seen cs ON cs.card_key = 'q:' || q.id AND cs.mode = ?"
        f" WHERE {' AND '.join(where)} ORDER BY {', '.join(order)}"
        + (" LIMIT ?" if limit else ""))
    rows = conn.execute(sql, tuple(params) + ((limit,) if limit else ())).fetchall()
    library = statute_index.load_library(config.STATUTE_DIR)
    cards = [_to_card(r, library) for r in rows]
    for card, row in zip(cards, rows):
        card["unseen"] = bool(row["unseen"])
    return cards


def by_article(conn, law_key: str, no: int, sub: int = 0,
               limit: int = 20) -> list[dict]:
    """某一条法条下的题目（法条页挂题）。basis 写法不统一，按条号串粗筛后逐条核验。"""
    label = statute_index.int2cn(no) + (
        f"之{statute_index.int2cn(sub)}" if sub else "")
    rows = conn.execute(
        "SELECT " + _COLS + " FROM quizzes"
        f" WHERE {_FILTER} AND basis LIKE ? ORDER BY id LIMIT ?",
        (quiz_bank.ORIGIN_BANK, quiz_bank.ORIGIN_JUDGE, f"%第{label}条%",
         max(limit * 4, 40))).fetchall()
    library = statute_index.load_library(config.STATUTE_DIR)
    out: list[dict] = []
    for row in rows:
        card = _to_card(row, library)
        if (card["law_key"], card["no"], card["sub"]) == (law_key, no, sub):
            out.append(card)
        if len(out) >= limit:
            break
    return out


def listen_text(card: dict) -> str:
    """听学法条卡的朗读文本：依据 → 条文 → 题干 → 答案 → 解析。"""
    lines = [f"法条依据：{card['basis']}。"]
    if card["article_text"]:
        lines.append(f"条文原文：{snippet(card['article_text'])}。")
    lines.append(f"题目：{card['stem']}")
    if card["options"]:
        lines.append("选项：" + "；".join(card["options"]) + "。")
    lines.append(f"答案：{card['answer']}。")
    if card["analysis"]:
        lines.append(f"解析：{card['analysis']}")
    return "\n".join(lines)


def stats(conn) -> dict:
    """池子规模与看背/听学进度（供看板与审计用）。"""
    ensure_table(conn)
    total = conn.execute(
        f"SELECT COUNT(*) c FROM quizzes WHERE {_FILTER}",
        (quiz_bank.ORIGIN_BANK, quiz_bank.ORIGIN_JUDGE)).fetchone()["c"]
    seen = {mode: conn.execute(
        "SELECT COUNT(*) c FROM card_seen WHERE mode=?", (mode,)).fetchone()["c"]
        for mode in MODES}
    return {"total": total, "seen": seen}


def for_plan(conn, plan: dict, mode: str = "read") -> list[dict]:
    """按今日计划配额取法条卡：每 3 张留 1 张，科目跟随今日计划，未看过优先。"""
    quota = max(1, (plan.get("quota") or 0) // 3)
    focus = list(dict.fromkeys(
        it["subject"] for it in plan.get("items", []) if it.get("subject")))
    return pool(conn, subjects=focus or None, mode=mode, limit=quota)


def card_by_id(conn, quiz_id: int) -> dict | None:
    """按 quiz_id 取一张法条卡（听学音频按需合成时用）。"""
    row = conn.execute(f"SELECT {_COLS} FROM quizzes WHERE id=?",
                       (quiz_id,)).fetchone()
    if row is None:
        return None
    return _to_card(row, statute_index.load_library(config.STATUTE_DIR))
