"""跨模块服务层：今日计划、统计、自测、复盘、答疑上下文。

所有 AI 调用都走 ai 模块的兜底函数；本模块不直接访问 DeepSeek。
"""
import json
import re
from datetime import date, datetime

from app import ai
from app import config
from app import coverage as cov
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
    return {"date": day, "quota": row["quota"], "rationale": row["rationale"],
            "items": detail, "counts": counts}


def record_review(conn, entry_id: str, mode: str, result: str,
                  duration_sec: int = 0) -> None:
    conn.execute(
        "INSERT INTO reviews (entry_id, ts, mode, result, duration_sec) "
        "VALUES (?,?,?,?,?)",
        (entry_id, datetime.now().isoformat(timespec="seconds"),
         mode, result, duration_sec),
    )
    conn.commit()


def record_quiz_answer(conn, quiz_id: int, user_answer: str, correct: bool,
                       duration_sec: int = 0) -> None:
    conn.execute(
        "INSERT INTO quiz_answers (quiz_id, ts, user_answer, correct, duration_sec) "
        "VALUES (?,?,?,?,?)",
        (quiz_id, datetime.now().isoformat(timespec="seconds"),
         user_answer, int(correct), duration_sec),
    )
    conn.commit()


def _weak_submodule(conn) -> str | None:
    tree = coverage_payload(conn)
    best = None
    for subject, sdata in tree.items():
        for sub, subdata in sdata["submodules"].items():
            weak = subdata["states"].get("weak", 0)
            if weak and (best is None or weak > best[1]):
                best = (f"{subject}·{sub}", weak)
    return best[0] if best else None


def today_stats(conn, day: str | None = None) -> dict:
    day = day or date.today().isoformat()
    plan = plan_payload(conn, day)
    done = conn.execute(
        "SELECT COUNT(*) AS n FROM reviews WHERE mode='read' AND date(ts)=?",
        (day,),
    ).fetchone()["n"]
    quiz = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(correct),0) AS correct "
        "FROM quiz_answers WHERE date(ts)=?", (day,),
    ).fetchone()
    listen = conn.execute(
        "SELECT COALESCE(SUM(duration_sec),0) AS s FROM reviews "
        "WHERE mode='listen' AND date(ts)=?", (day,),
    ).fetchone()["s"]
    quota = plan["quota"] or 0
    percent = round(done / quota * 100) if quota else 0
    return {
        "date": day, "done": done, "quota": quota, "percent": percent,
        "quiz_total": quiz["total"], "quiz_correct": quiz["correct"],
        "listen_min": round(listen / 60), "counts": plan["counts"],
        "weak": _weak_submodule(conn) or "暂无",
    }


def build_daily_quiz(conn, day: str | None = None, limit: int = 10) -> list[dict]:
    day = day or date.today().isoformat()
    ensure_today_plan(conn, day)
    plan = plan_payload(conn, day)
    today_ids = [it["id"] for it in plan["items"]]
    wrong_ids = [
        r["entry_id"] for r in conn.execute(
            "SELECT DISTINCT q.entry_id FROM quiz_answers qa "
            "JOIN quizzes q ON qa.quiz_id=q.id "
            "WHERE qa.correct=0 AND q.entry_id IS NOT NULL"
        ).fetchall()
    ]
    selected: list[str] = []
    n_today = round(limit * 0.7)
    selected += [i for i in today_ids if i not in selected][:n_today]
    selected += [i for i in wrong_ids
                 if i not in selected and i not in today_ids]
    if len(selected) < limit:
        for i in today_ids:
            if len(selected) >= limit:
                break
            if i not in selected:
                selected.append(i)
    selected = selected[:limit]

    out = []
    for entry_id in selected:
        entry = _entry_by_id(conn, entry_id)
        if entry is None:
            continue
        cached = conn.execute(
            "SELECT id, qtype, stem, options, answer FROM quizzes "
            "WHERE entry_id=? AND date(created_at)=?", (entry_id, day)
        ).fetchone()
        if cached:
            quiz = {"id": cached["id"], "entry_id": entry_id,
                    "qtype": cached["qtype"], "stem": cached["stem"],
                    "options": json.loads(cached["options"] or "[]"),
                    "answer": cached["answer"]}
        else:
            quiz = ai.generate_quiz(entry) or ai.cloze_quiz(entry)
            cur = conn.execute(
                "INSERT INTO quizzes (entry_id, qtype, stem, options, answer, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (entry_id, quiz["qtype"], quiz["stem"],
                 json.dumps(quiz["options"], ensure_ascii=False),
                 quiz["answer"], datetime.now().isoformat(timespec="seconds")),
            )
            quiz = {**quiz, "id": cur.lastrowid, "entry_id": entry_id}
        out.append(quiz)
    conn.commit()
    return out


def coverage_payload(conn) -> dict:
    rows = conn.execute(
        "SELECT subject, submodule, point, "
        "(SELECT r.result FROM reviews r WHERE r.entry_id=e.id "
        " ORDER BY r.ts DESC LIMIT 1) AS last_result, "
        "(SELECT COUNT(*) FROM reviews r WHERE r.entry_id=e.id) AS review_count "
        "FROM entries e"
    ).fetchall()
    items = [
        {"subject": r["subject"], "submodule": r["submodule"],
         "point": r["point"], "state": cov.entry_state(r["last_result"], r["review_count"])}
        for r in rows
    ]
    return cov.coverage_tree(items)


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
    day = day or date.today().isoformat()
    existing = latest_report(conn, "morning")
    if existing and existing["date"] == day:
        return existing
    content = ai.generate_morning_report(plan_payload(conn, day), today_stats(conn, day))
    save_report(conn, day, "morning", content)
    return latest_report(conn, "morning")


def evening_report(conn, day: str | None = None, force: bool = False) -> dict | None:
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
