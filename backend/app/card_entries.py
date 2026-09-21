"""法条题卡条目化：把已发布的法条驱动题重建为 entries 行（kind='card'）。

卡片是题库（quizzes）的派生数据：ID、正文、朗读内容全由题目决定，
`scripts/sync_card_entries.py` 幂等重建。看背 / 听学 / 标记 / 三档自评 / 音频
全部复用条目那一条代码路径（见 docs/superpowers/specs/2026-09-20-法条题卡条目化统一-design.md）。
"""
import json

from app import config, quiz_bank, statute_cards, statute_index

#: 卡片 ID = <科目前缀>-Q<quiz_id 六位>，如 XF-Q000162
CARD_MARK = "-Q"
#: 科目前缀（与 scripts/generate_entries.py 的 SUBJECT_PREFIX 保持一致）
SUBJECT_PREFIX = {
    "刑法": "XF", "民法": "MF", "刑诉": "XS", "民诉": "MS",
    "商经知劳环": "SJ", "理论法": "LL", "三国法": "SG", "行政法": "XZ",
}
UNKNOWN_PREFIX = "QT"
#: 卡片统一普通优先级：高优先级条目学完自然轮到（不做强制混排）
CARD_PRIORITY = "普通"
#: 卡片只做客观题（用户 2026-09-20 明确：判断题不进卡片）
CARD_ORIGINS = (quiz_bank.ORIGIN_BANK,)
SUBJECT_FALLBACK = "法条题"
POINT_STEM_CHARS = 24
#: 每批提交条数（3 万张卡片：逐条 commit 会让同步慢一个数量级）
BATCH = 500

ENTRY_COLS = ("id", "kind", "subject", "submodule", "point", "anchor", "conclusion",
              "priority", "rationale", "sources", "cases", "statutes", "note",
              "tts_text", "options", "article_text", "status")


def entry_id_for(subject: str, quiz_id: int) -> str:
    """题目科目 + quiz_id → 卡片条目 ID。"""
    return f"{SUBJECT_PREFIX.get(subject, UNKNOWN_PREFIX)}{CARD_MARK}{quiz_id:06d}"


def quiz_id_of(entry_id: str) -> int | None:
    """卡片条目 ID → quiz_id（正式条目返回 None）。"""
    if CARD_MARK not in entry_id:
        return None
    tail = entry_id.rsplit(CARD_MARK, 1)[1]
    return int(tail) if tail.isdigit() else None


def _label(law_key: str, no: int, sub: int) -> str:
    """「中华人民共和国刑法」+269 → 刑法第二百六十九条（子条带「之N」）。"""
    label = f"{law_key.replace('中华人民共和国', '')}第{statute_index.int2cn(no)}条"
    return f"{label}之{statute_index.int2cn(sub)}" if sub else label


def _clip(text: str, limit: int) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit]


def payload(row, library: dict | None = None) -> dict:
    """quizzes 行 → 卡片条目字段（一次性算全，便于逐字段比对漂移）。"""
    card = statute_cards.card_from_row(row, library)
    law_key = card["law_key"] or ""
    title = (_label(law_key, card["no"], card["sub"]) if law_key
             else (card["basis"] or SUBJECT_FALLBACK))
    return {
        "id": entry_id_for(row["subject"], row["id"]),
        "kind": "card",
        "subject": row["subject"],
        "submodule": law_key or SUBJECT_FALLBACK,
        "point": f"{title} · {_clip(card['stem'], POINT_STEM_CHARS)}",
        "anchor": card["stem"],
        "conclusion": card["answer"],
        "priority": CARD_PRIORITY,
        "rationale": card["analysis"],
        "sources": "[]",
        "cases": "[]",
        "statutes": json.dumps([card["basis"]] if card["basis"] else [],
                               ensure_ascii=False),
        "note": None,
        "tts_text": statute_cards.listen_text(card),
        "options": row["options"] or "[]",
        "article_text": statute_cards.snippet(card["article_text"]),
        "status": "final",
    }


def _changed(old, new: dict) -> bool:
    """逐字段比对（不用额外 hash 列，文本变了必然能被发现）。"""
    return any(old[c] != new[c] for c in ENTRY_COLS if c != "id")


def _drop_audio(conn, entry_id: str) -> None:
    """朗读文本变了：旧音频与台账一并作废，下次进听学时按需重合成。"""
    try:
        (config.AUDIO_DIR / f"{entry_id}.wav").unlink(missing_ok=True)
    except OSError:
        pass
    conn.execute("DELETE FROM tts_assets WHERE entry_id=?", (entry_id,))


def upsert(conn, row, library: dict | None = None, *, dry_run: bool = False) -> str:
    """写一张卡片，返回 created / updated / unchanged / archived（不提交事务）。"""
    new = payload(row, library)
    old = conn.execute("SELECT * FROM entries WHERE id=?", (new["id"],)).fetchone()
    if old is not None and not _changed(old, new):
        return "unchanged"
    if dry_run:
        return "created" if old is None else "updated"
    if old is None:
        conn.execute(
            f"INSERT INTO entries ({', '.join(ENTRY_COLS)})"
            f" VALUES ({', '.join('?' * len(ENTRY_COLS))})",
            [new[c] for c in ENTRY_COLS])
        return "created"
    if old["tts_text"] != new["tts_text"]:
        _drop_audio(conn, new["id"])
    sets = ", ".join(f"{c}=?" for c in ENTRY_COLS if c != "id")
    conn.execute(f"UPDATE entries SET {sets} WHERE id=?",
                 [new[c] for c in ENTRY_COLS if c != "id"] + [new["id"]])
    return "updated"


def published_rows(conn, subjects: list[str] | None = None, limit: int = 0):
    """题库侧卡片来源：已发布的客观题（判断题不做卡片）、不挂条目、有法条依据。"""
    sql = ("SELECT id, subject, qtype, stem, options, answer, analysis, basis"
           f" FROM quizzes WHERE origin IN ({','.join('?' * len(CARD_ORIGINS))})"
           " AND status='published' AND entry_id IS NULL AND basis != ''")
    params: list = list(CARD_ORIGINS)
    if subjects:
        sql += f" AND subject IN ({','.join('?' * len(subjects))})"
        params += list(subjects)
    sql += " ORDER BY id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def _cleanup(conn, published_ids: set[str], subjects: list[str] | None,
             *, dry_run: bool) -> int:
    """卡片与题库对齐，返回处理的条数。

    - 题库下架（archived/draft）→ 卡片转 draft：保留行与答题历史，不进队列；
    - 题目不再是卡片来源（判断题、题目已删除）→ 删除卡片行与其音频。
    """
    rows = conn.execute("SELECT id, subject FROM entries WHERE kind='card'").fetchall()
    stale = [r for r in rows
             if r["id"] not in published_ids
             and (not subjects or r["subject"] in subjects)]
    if not stale:
        return 0
    quiz_ids = [q for q in (quiz_id_of(r["id"]) for r in stale) if q is not None]
    meta: dict[int, tuple[str, str]] = {}
    if quiz_ids:
        placeholders = ",".join("?" * len(quiz_ids))
        meta = {r["id"]: (r["origin"], r["status"]) for r in conn.execute(
            f"SELECT id, origin, status FROM quizzes WHERE id IN ({placeholders})",
            quiz_ids)}
    to_draft: list[str] = []
    to_delete: list[str] = []
    for r in stale:
        info = meta.get(quiz_id_of(r["id"]) or 0)
        if info is None or info[0] not in CARD_ORIGINS:
            to_delete.append(r["id"])       # 判断题/题目已删：卡片本身不该存在
        else:
            to_draft.append(r["id"])        # 题库下架：留行，转 draft
    if not dry_run:
        if to_delete:
            conn.executemany("DELETE FROM entries WHERE id=?",
                             [(i,) for i in to_delete])
            conn.executemany("DELETE FROM tts_assets WHERE entry_id=?",
                             [(i,) for i in to_delete])
        if to_draft:
            conn.executemany("UPDATE entries SET status='draft' WHERE id=?",
                             [(i,) for i in to_draft])
    return len(stale)


def sync(conn, *, subjects: list[str] | None = None, limit: int = 0,
         dry_run: bool = False) -> dict:
    """幂等重建卡片条目；返回 created/updated/unchanged/archived/total。"""
    library = statute_index.load_library(config.STATUTE_DIR)
    rows = published_rows(conn, subjects, limit)
    counts = {"created": 0, "updated": 0, "unchanged": 0, "cleaned": 0,
              "total": len(rows)}
    published_ids: set[str] = set()
    for i, row in enumerate(rows, 1):
        published_ids.add(entry_id_for(row["subject"], row["id"]))
        counts[upsert(conn, row, library, dry_run=dry_run)] += 1
        if not dry_run and i % BATCH == 0:
            conn.commit()
    if not limit:
        counts["cleaned"] = _cleanup(conn, published_ids, subjects, dry_run=dry_run)
    if not dry_run:
        conn.commit()
    return counts


def stats(conn) -> dict:
    """卡片与题目的 1:1 核对口径（供脚本与审计使用）。"""
    return {
        "entries": conn.execute("SELECT COUNT(*) c FROM v_entries").fetchone()["c"],
        "cards": conn.execute("SELECT COUNT(*) c FROM entries WHERE kind='card'").fetchone()["c"],
        "final": conn.execute(
            "SELECT COUNT(*) c FROM entries WHERE kind='card' AND status='final'"
        ).fetchone()["c"],
        "published": conn.execute(
            f"SELECT COUNT(*) c FROM quizzes WHERE"
            f" origin IN ({','.join('?' * len(CARD_ORIGINS))})"
            " AND status='published' AND entry_id IS NULL AND basis != ''",
            CARD_ORIGINS).fetchone()["c"],
    }


def coverage(conn) -> dict:
    """题卡覆盖：科目 → 法条主名 → {count, unread}，供「自定义范围」按法条选题卡。"""
    rows = conn.execute(
        """
        SELECT e.subject AS subject, e.submodule AS law,
               COUNT(*) AS count,
               COUNT(CASE WHEN NOT EXISTS (SELECT 1 FROM reviews r
                       WHERE r.entry_id=e.id AND r.mode='read') THEN 1 END) AS unread
        FROM entries e WHERE e.kind='card' AND e.status='final'
        GROUP BY e.subject, e.submodule
        """
    ).fetchall()
    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        out.setdefault(r["subject"], {})[r["law"]] = {
            "count": r["count"], "unread": r["unread"]}
    return out
