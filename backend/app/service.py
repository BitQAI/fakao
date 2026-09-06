"""跨模块服务层：今日计划、统计、自测、复盘、答疑上下文。

所有 AI 调用都走 ai 模块的兜底函数；本模块不直接访问 DeepSeek。
"""
import json
import re
from datetime import date, datetime

from app import ai
from app import config
from app import coverage as cov
from app import generator
from app import review_stats
from app import scheduler

_WORD_SPLIT = re.compile(r"[\s，。、；：？！,.;:?!()（）]+")


def get_setting(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                 (key, value))
    conn.commit()


def days_left(conn, today: str | None = None) -> int | None:
    exam = get_setting(conn, "exam_date", "").strip()
    if not exam:
        return None
    today = today or date.today().isoformat()
    return (date.fromisoformat(exam) - date.fromisoformat(today)).days


def _entry_dict(r) -> dict:
    return {
        "id": r["id"], "subject": r["subject"], "submodule": r["submodule"],
        "point": r["point"], "anchor": r["anchor"], "conclusion": r["conclusion"],
        "priority": r["priority"], "rationale": r["rationale"],
        "sources": json.loads(r["sources"] or "[]"),
        "cases": json.loads(r["cases"] or "[]"),
        "statutes": json.loads(r["statutes"] or "[]"), "note": r["note"],
        "tts_text": r["tts_text"],
    }


def _entry_by_id(conn, entry_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    return _entry_dict(r) if r else None


def entry_by_id(conn, entry_id: str) -> dict | None:
    """公开入口：按 id 取单条 final 条目（供深链/历史跳转）。"""
    r = conn.execute("SELECT * FROM entries WHERE id=? AND status='final'",
                     (entry_id,)).fetchone()
    if r is None:
        return None
    e = _entry_dict(r)
    review_stats.attach_read_counts(conn, [e])
    review_stats.attach_listen_counts(conn, [e])
    review_stats.attach_listened_today(conn, [e])
    review_stats.attach_reviewed_today(conn, [e])
    return e


def _recent_daily_counts(conn, day: str) -> list[int]:
    rows = conn.execute(
        "SELECT date(ts) AS d, COUNT(*) AS n FROM reviews "
        "WHERE mode IN ('read','quiz') AND date(ts) < ? "
        "GROUP BY d ORDER BY d DESC LIMIT 3",
        (day,),
    ).fetchall()
    return [r["n"] for r in rows]


def ensure_today_plan(conn, day: str | None = None) -> dict:
    day = day or date.today().isoformat()
    existing = conn.execute("SELECT date FROM daily_plans WHERE date=?",
                            (day,)).fetchone()
    if existing:
        return plan_payload(conn, day)

    rows = conn.execute(
        """
        SELECT e.id, e.subject, e.submodule, e.point, e.priority,
               (SELECT r.ts FROM reviews r WHERE r.entry_id=e.id
                ORDER BY r.ts DESC LIMIT 1) AS last_ts,
               (SELECT r.result FROM reviews r WHERE r.entry_id=e.id
                ORDER BY r.ts DESC LIMIT 1) AS last_result,
               EXISTS(SELECT 1 FROM quiz_answers qa JOIN quizzes q ON qa.quiz_id=q.id
                      WHERE q.entry_id=e.id AND qa.correct=0) AS wrong_ever
        FROM entries e WHERE e.status='final'
        """
    ).fetchall()

    states = []
    for r in rows:
        st = scheduler.classify(r["id"], r["subject"], r["submodule"], r["point"],
                                r["priority"], r["last_ts"], r["last_result"],
                                bool(r["wrong_ever"]), day)
        if st is not None:
            states.append(st)

    cap_max = int(get_setting(conn, "capacity_max", "50") or "50")
    capacity = scheduler.compute_capacity(_recent_daily_counts(conn, day), cap_max)
    stats = {
        "days_left": days_left(conn, day),
        "total_entries": len(states),
        "retry_n": sum(1 for s in states if s.bucket == "retry"),
        "review_n": sum(1 for s in states if s.bucket == "review"),
        "new_n": sum(1 for s in states if s.bucket == "new"),
        "capacity_max": cap_max,
    }
    ratio = ai.adjust_plan_ratio(stats)
    queue = scheduler.build_queue(states, capacity, ratio)
    state_by_id = {s.entry_id: s.bucket for s in states}
    items = [{"entry_id": eid, "bucket": state_by_id[eid]} for eid in queue]
    rationale = ai.generate_daily_rationale({**stats, "quota": len(queue)})
    conn.execute(
        "INSERT OR REPLACE INTO daily_plans (date, items, quota, rationale) "
        "VALUES (?,?,?,?)",
        (day, json.dumps(items, ensure_ascii=False), len(queue), rationale),
    )
    conn.commit()
    return plan_payload(conn, day)


def plan_payload(conn, day: str) -> dict:
    row = conn.execute("SELECT items, quota, rationale FROM daily_plans "
                       "WHERE date=?", (day,)).fetchone()
    if row is None:
        return {"date": day, "quota": 0, "rationale": "", "items": [],
                "counts": {"retry": 0, "review": 0, "new": 0}}
    items = json.loads(row["items"])
    counts = {"retry": 0, "review": 0, "new": 0}
    ids = []
    for it in items:
        counts[it["bucket"]] += 1
        ids.append(it["entry_id"])
    by_id = {}
    if ids:
        placeholders = ",".join("?" * len(ids))
        for r in conn.execute(
            f"SELECT * FROM entries WHERE id IN ({placeholders})", ids
        ).fetchall():
            by_id[r["id"]] = _entry_dict(r)
    detail = []
    for it in items:
        e = by_id.get(it["entry_id"])
        if e is None:
            continue
        e["bucket"] = it["bucket"]
        detail.append(e)
    review_stats.attach_read_counts(conn, detail)
    review_stats.attach_reviewed_today(conn, detail, day)
    return {"date": day, "quota": row["quota"], "rationale": row["rationale"],
            "items": detail, "counts": counts}


def continue_plan_entries(conn, count: int = 5) -> list[dict]:
    """看背续学：今日计划之外的候选条目，按 错题>复习>新学 > 优先级 > 科目顺序 取前 N。"""
    day = date.today().isoformat()
    plan = plan_payload(conn, day)
    plan_ids = {it["id"] for it in plan["items"]}
    rows = conn.execute(
        """
        SELECT e.id, e.subject, e.submodule, e.point, e.priority,
               (SELECT r.ts FROM reviews r WHERE r.entry_id=e.id
                ORDER BY r.ts DESC LIMIT 1) AS last_ts,
               (SELECT r.result FROM reviews r WHERE r.entry_id=e.id
                ORDER BY r.ts DESC LIMIT 1) AS last_result,
               EXISTS(SELECT 1 FROM quiz_answers qa JOIN quizzes q ON qa.quiz_id=q.id
                      WHERE q.entry_id=e.id AND qa.correct=0) AS wrong_ever
        FROM entries e WHERE e.status='final'
        """
    ).fetchall()
    bucket_rank = {"retry": 0, "review": 1, "new": 2}
    states = []
    for r in rows:
        if r["id"] in plan_ids:
            continue
        st = scheduler.classify(r["id"], r["subject"], r["submodule"], r["point"],
                                r["priority"], r["last_ts"], r["last_result"],
                                bool(r["wrong_ever"]), day)
        if st is not None:
            states.append(st)
    states.sort(key=lambda s: (
        bucket_rank[s.bucket],
        scheduler.PRIORITY_ORDER.get(s.priority, 9),
        scheduler.SUBJECT_ORDER.index(s.subject)
        if s.subject in scheduler.SUBJECT_ORDER else len(scheduler.SUBJECT_ORDER),
        s.entry_id,
    ))
    selected = [s.entry_id for s in states[:count]]
    bucket_by_id = {s.entry_id: s.bucket for s in states}
    items = []
    if selected:
        placeholders = ",".join("?" * len(selected))
        by_id = {}
        for r in conn.execute(
            f"SELECT * FROM entries WHERE id IN ({placeholders})", selected
        ).fetchall():
            by_id[r["id"]] = _entry_dict(r)
        for eid in selected:
            e = by_id.get(eid)
            if e is not None:
                e["bucket"] = bucket_by_id.get(eid, "new")
                items.append(e)
    return review_stats.attach_reviewed_today(
        conn, review_stats.attach_read_counts(conn, items), day)


def custom_entries(conn, subjects: list[str] | None = None,
                   points: list[str] | None = None, limit: int | None = None,
                   listen_only: bool = False,
                   exclude: list[str] | None = None) -> list[dict]:
    """自定义学习范围：科目/知识点并集过滤，优先级×科目顺序排序。

    limit 仅作安全上限；调用方如需分批取数，可自行按返回列表切片并传 exclude。

    排序：读/听次数少优先 → 优先级 → 科目顺序 → id
    """
    subjects = [s for s in (subjects or []) if s]
    points = [p for p in (points or []) if p]
    exclude = [x for x in (exclude or []) if x]
    if not subjects and not points:
        return []
    union = []
    if subjects:
        union.append(f"e.subject IN ({','.join('?' * len(subjects))})")
    if points:
        union.append(f"e.point IN ({','.join('?' * len(points))})")
    conds = []
    if union:
        conds.append("(" + " OR ".join(union) + ")")
    if listen_only:
        conds.append("e.tts_text != ''")
    if exclude:
        conds.append(f"e.id NOT IN ({','.join('?' * len(exclude))})")
    sql = "SELECT * FROM entries e WHERE e.status='final'"
    if conds:
        sql += " AND " + " AND ".join(conds)
    rows = conn.execute(sql, subjects + points + exclude).fetchall()
    items = [_entry_dict(r) for r in rows]
    # 批量附加 read_count / listen_count
    items = review_stats.attach_read_counts(conn, items)
    items = review_stats.attach_listen_counts(conn, items)
    # 排序：未读/未听优先 → 次数少优先 → 久未听优先 → 优先级 → 科目顺序 → id
    if listen_only:
        items = _sort_listen_items(items)
    else:
        items.sort(key=lambda e: (
            e.get("read_count", 0),    # 未读(0)优先
            scheduler.PRIORITY_ORDER.get(e["priority"], 9),
            scheduler.SUBJECT_ORDER.index(e["subject"])
            if e["subject"] in scheduler.SUBJECT_ORDER else len(scheduler.SUBJECT_ORDER),
            e["id"],
        ))
    if limit is not None:
        items = items[:limit]
    items = review_stats.attach_reviewed_today(conn, items)
    items = review_stats.attach_listened_today(conn, items)
    return items


def record_review(conn, entry_id: str, mode: str, result: str,
                  duration_sec: int = 0) -> None:
    conn.execute(
        "INSERT INTO reviews (entry_id, ts, mode, result, duration_sec) "
        "VALUES (?,?,?,?,?)",
        (entry_id, datetime.now().isoformat(timespec="seconds"),
         mode, result, duration_sec),
    )
    conn.commit()


def latest_report(conn, kind: str) -> dict | None:
    row = conn.execute(
        "SELECT id, date, kind, content, created_at FROM reports "
        "WHERE kind=? ORDER BY date DESC, id DESC LIMIT 1", (kind,)
    ).fetchone()
    return dict(row) if row else None


def save_report(conn, day: str, kind: str, content: str) -> None:
    conn.execute(
        "INSERT INTO reports (date, kind, content, created_at) VALUES (?,?,?,?)",
        (day, kind, content, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def morning_report(conn, day: str | None = None) -> dict | None:
    from app.stats import today_stats

    day = day or date.today().isoformat()
    existing = latest_report(conn, "morning")
    if existing and existing["date"] == day:
        return existing
    plan = ensure_today_plan(conn, day)
    content = ai.generate_morning_report(
        {**plan,
         "new_n": plan["counts"]["new"],
         "review_n": plan["counts"]["review"],
         "retry_n": plan["counts"]["retry"]},
        today_stats(conn, day),
    )
    save_report(conn, day, "morning", content)
    return latest_report(conn, "morning")


def evening_report(conn, day: str | None = None, force: bool = False) -> dict | None:
    from app.stats import today_stats

    day = day or date.today().isoformat()
    existing = latest_report(conn, "evening")
    if existing and existing["date"] == day and not force:
        return existing
    content = ai.generate_evening_report(today_stats(conn, day))
    save_report(conn, day, "evening", content)
    return latest_report(conn, "evening")


def _search_entries(conn, question: str, limit: int = 5) -> list[dict]:
    tokens = [t for t in _WORD_SPLIT.split(question) if t][:4]
    if not tokens:
        return []
    conds = " OR ".join(["point LIKE ?"] * len(tokens))
    rows = conn.execute(
        f"SELECT * FROM entries WHERE {conds} LIMIT ?",
        (*[f"%{t}%" for t in tokens], limit),
    ).fetchall()
    return [_entry_dict(r) for r in rows]


def assistant_context(conn, question: str,
                      entry_id: str | None = None) -> tuple[str, list[str], list[str]]:
    related: list[dict] = []
    ids: list[str] = []
    if entry_id:
        e = _entry_by_id(conn, entry_id)
        if e:
            related.append(e)
            ids.append(entry_id)
    for e in _search_entries(conn, question, limit=5):
        if e["id"] not in ids:
            related.append(e)
            ids.append(e["id"])
    lines = []
    source_refs: list[str] = []
    for e in related:
        lines.append(
            f"[{e['id']}|{e['subject']}·{e['submodule']}] {e['point']}\n"
            f"场景：{e['anchor']}\n结论：{e['conclusion']}\n"
            f"法条：{'；'.join(e['statutes'])}\n"
            + (f"陷阱：{e['note']}\n" if e["note"] else "")
        )
        for s in e["sources"]:
            ref = s.get("ref", "")
            if not ref:
                continue
            source_refs.append(f"{s.get('type', '')}:{ref}")
            src_file = next(config.SOURCE_DIR.glob(f"**/{ref}"), None)
            if src_file is not None and src_file.exists():
                snippet = src_file.read_text(encoding="utf-8-sig")[:800]
                lines.append(f"—— 出处 {ref} 节选：\n{snippet}")
    return "\n".join(lines), ids, list(dict.fromkeys(source_refs))[:10]


def record_chat(conn, question: str, answer: str,
                related_ids: list[str], source_refs: list[str]) -> None:
    conn.execute(
        "INSERT INTO chat_logs (ts, question, answer, related_entry_ids, source_refs) "
        "VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), question, answer,
         json.dumps(related_ids, ensure_ascii=False),
         json.dumps(source_refs, ensure_ascii=False)),
    )
    conn.commit()


def _sort_listen_items(items: list[dict]) -> list[dict]:
    """听学统一排序：未听优先 → 次数少优先 → 久未听优先 → 优先级 → 科目 → id。"""
    never: list[tuple] = []
    heard: list[tuple] = []
    for e in items:
        cnt = e.get("listen_count", 0) or 0
        last = e.get("last_ts")
        prio_rank = scheduler.PRIORITY_ORDER.get(e.get("priority"), 9)
        subj = e.get("subject")
        subj_rank = (scheduler.SUBJECT_ORDER.index(subj)
                     if subj in scheduler.SUBJECT_ORDER
                     else len(scheduler.SUBJECT_ORDER))
        tup = (e, cnt, last or "", prio_rank, subj_rank, e.get("id", ""))
        (never if cnt == 0 else heard).append(tup)
    never.sort(key=lambda t: (t[3], t[4], t[5]))
    heard.sort(key=lambda t: (t[1], t[2], t[3], t[4], t[5]))
    return [t[0] for t in never + heard]


def _listen_pool(conn, exclude: set[str] | None = None):
    """听学池排序（未听过优先；已听按听过次数少优先、同次数则越久未听越优先），可排除 id 集合。

    返回 (items, remaining)，每条 item 附 listen_count / last_ts / listened_today 供前端标记已听。
    """
    exclude = exclude or set()
    rows = conn.execute(
        """
        SELECT e.*,
               (SELECT COUNT(*) FROM reviews r
                WHERE r.entry_id=e.id AND r.mode='listen') AS listen_cnt,
               (SELECT MAX(r.ts) FROM reviews r
                WHERE r.entry_id=e.id AND r.mode='listen') AS last_ts
        FROM entries e
        WHERE e.status='final' AND e.tts_text != ''
        """).fetchall()
    remaining = conn.execute(
        """
        SELECT COUNT(*) AS n FROM entries e
        WHERE e.status='final' AND e.tts_text != ''
          AND NOT EXISTS (SELECT 1 FROM reviews r
                          WHERE r.entry_id=e.id AND r.mode='listen')
        """).fetchone()["n"]
    items: list[dict] = []
    for r in rows:
        if r["id"] in exclude:
            continue
        e = _entry_dict(r)
        e["listen_count"] = r["listen_cnt"]
        e["last_ts"] = r["last_ts"]
        items.append(e)
    items = _sort_listen_items(items)
    items = review_stats.attach_listened_today(conn, items)
    items = review_stats.attach_reviewed_today(conn, items)
    return items, remaining


def listen_queue(conn, limit: int = 10) -> dict:
    """听学池：未听过优先，已听按最近听过倒序；返回已听标记与累计进度。"""
    items, remaining = _listen_pool(conn)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 10
    limit = min(max(limit, 1), 500)
    slice_items = items[:limit]
    heard_total = conn.execute(
        """
        SELECT COUNT(DISTINCT r.entry_id) AS n
        FROM reviews r JOIN entries e ON e.id = r.entry_id
        WHERE r.mode='listen' AND e.status='final' AND e.tts_text != ''
        """).fetchone()["n"]
    return {"items": slice_items, "remaining": remaining,
            "heard_total": heard_total}


def listen_more(conn, exclude: list[str], count: int = 5) -> dict:
    """听学续学：返回当前队列之外的下 N 条（同一排序）。"""
    items, remaining = _listen_pool(conn, set(exclude or []))
    slice_items = items[:count]
    return {"items": slice_items, "remaining": remaining}


def ensure_listen_pool(conn, threshold: int = 50) -> bool:
    """剩余可听数低于阈值时触发后台生成；返回是否触发。"""
    if listen_queue(conn, limit=1)["remaining"] >= threshold:
        return False
    return generator.ensure_generation(conn)


ENTRY_TEXT_PRIORITIES = ("高频考点", "易错陷阱", "新增必考", "普通")


def update_entry_text(conn, entry_id: str, fields: dict) -> tuple[dict | None, str | None]:
    """看背就地更正：仅允许文本字段（不碰 tts/音频/status）。

    返回 (entry, error)：成功时 error 为 None；失败时 entry 为 None。
    校验对齐 importer（锚点 16-36 字、结论 ≤60 且以“。”结尾、priority 枚举）。
    """
    row = conn.execute("SELECT id FROM entries WHERE id=? AND status='final'",
                       (entry_id,)).fetchone()
    if row is None:
        return None, "条目不存在"
    point = (fields.get("point") or "").strip()
    anchor = (fields.get("anchor") or "").strip()
    conclusion = (fields.get("conclusion") or "").strip()
    priority = (fields.get("priority") or "").strip()
    note = fields.get("note")
    note = None if note is None or not str(note).strip() else str(note).strip()
    if not point:
        return None, "point 不能为空"
    if not 16 <= len(anchor) <= 36:
        return None, f"锚点句长度 {len(anchor)} 不在 16-36 内"
    if not conclusion or len(conclusion) > 60 or not conclusion.endswith("。"):
        return None, "结论句超长或未以句号结尾（≤60 且以“。”结尾）"
    if priority not in ENTRY_TEXT_PRIORITIES:
        return None, f"优先级非法: {priority!r}"
    conn.execute(
        "UPDATE entries SET point=?, anchor=?, conclusion=?, note=?, priority=? "
        "WHERE id=?",
        (point, anchor, conclusion, note, priority, entry_id),
    )
    conn.commit()
    return entry_by_id(conn, entry_id), None


def chat_history_for_entry(conn, entry_id: str, limit: int = 20) -> list[dict]:
    """按条目取 AI 问答历史：Python 侧解析 related_entry_ids 精确匹配。

    不用 LIKE，避免 XF-001 误配 XF-0010 等前缀 id。
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = min(max(limit, 1), 50)
    rows = conn.execute(
        "SELECT id, ts, question, answer, related_entry_ids FROM chat_logs "
        "ORDER BY id DESC LIMIT 200"
    ).fetchall()
    out = []
    for r in rows:
        try:
            ids = json.loads(r["related_entry_ids"] or "[]")
        except (ValueError, TypeError):
            ids = []
        if entry_id in ids:
            out.append({
                "id": r["id"], "ts": r["ts"], "question": r["question"],
                "answer": r["answer"], "related_entry_ids": ids,
            })
        if len(out) >= limit:
            break
    return out
