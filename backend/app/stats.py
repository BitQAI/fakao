"""统计模块（自 service.py 拆分）：今日统计、覆盖树、错题本、连胜与趋势。

口径（spec 2026-08-31）：完成率 = 看背 + 自测；覆盖树状态与 scheduler 对齐。
"""
from datetime import date, timedelta

from app import coverage as cov
from app import review_stats, scheduler, service
from app.service import _entry_dict, plan_payload


def _weak_submodule(conn) -> str | None:
    tree = coverage_payload(conn)
    best = None
    for subject, sdata in tree.items():
        for sub, subdata in sdata["submodules"].items():
            weak = subdata["states"].get("weak", 0)
            if weak and (best is None or weak > best[1]):
                best = (f"{subject}·{sub}", weak)
    return best[0] if best else None


def coverage_payload(conn) -> dict:
    rows = conn.execute(
        "SELECT subject, submodule, point, "
        "(SELECT r.result FROM reviews r WHERE r.entry_id=e.id "
        " ORDER BY r.ts DESC LIMIT 1) AS last_result, "
        "(SELECT COUNT(*) FROM reviews r WHERE r.entry_id=e.id "
        " AND r.mode='read') AS read_count, "
        "NOT EXISTS(SELECT 1 FROM reviews r WHERE r.entry_id=e.id "
        " AND r.mode='read') AS unread, "
        "NOT EXISTS(SELECT 1 FROM reviews r WHERE r.entry_id=e.id "
        " AND r.mode='listen') AS unlistened, "
        "EXISTS(SELECT 1 FROM quiz_answers qa JOIN quizzes q ON qa.quiz_id=q.id "
        " WHERE q.entry_id=e.id AND qa.correct=0) AS quiz_wrong, "
        "EXISTS(SELECT 1 FROM reviews r WHERE r.entry_id=e.id) "
        " OR EXISTS(SELECT 1 FROM quiz_answers qa JOIN quizzes q ON qa.quiz_id=q.id "
        " WHERE q.entry_id=e.id) AS has_record "
        "FROM entries e"
    ).fetchall()
    items = [
        {"subject": r["subject"], "submodule": r["submodule"],
         "point": r["point"], "unread": bool(r["unread"]),
         "unlistened": bool(r["unlistened"]),
         "state": cov.entry_state(r["last_result"], r["read_count"],
                                  bool(r["quiz_wrong"]), bool(r["has_record"]))}
        for r in rows
    ]
    return cov.coverage_tree(items)


def today_stats(conn, day: str | None = None) -> dict:
    day = day or date.today().isoformat()
    plan = plan_payload(conn, day)
    read_done = conn.execute(
        "SELECT COUNT(*) AS n FROM reviews WHERE mode='read' AND date(ts)=?",
        (day,),
    ).fetchone()["n"]
    quiz_done = conn.execute(
        "SELECT COUNT(*) AS n FROM quiz_answers WHERE date(ts)=?",
        (day,),
    ).fetchone()["n"]
    done = read_done + quiz_done
    quiz = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(correct),0) AS correct "
        "FROM quiz_answers WHERE date(ts)=?", (day,),
    ).fetchone()
    listen = conn.execute(
        "SELECT COALESCE(SUM(duration_sec),0) AS s FROM reviews "
        "WHERE mode='listen' AND date(ts)=?", (day,),
    ).fetchone()["s"]
    quota = plan["quota"] or 0
    percent = min(100, round(done / quota * 100)) if quota else 0
    return {
        "date": day, "done": done, "quota": quota, "percent": percent,
        "over_done": quota > 0 and done > quota,
        "quiz_total": quiz["total"], "quiz_correct": quiz["correct"],
        "listen_min": round(listen / 60), "counts": plan["counts"],
        "weak": _weak_submodule(conn) or "暂无",
        "days_left": service.days_left(conn, day),
    }


def wrongbook(conn, limit: int = 200) -> list[dict]:
    """错题本：聚合 quiz 答错 + 看背 bad，按最近错误时间倒序。"""
    rows = conn.execute(
        """
        SELECT * FROM (
          SELECT e.id, e.subject, e.submodule, e.point, e.anchor, e.conclusion,
                 e.priority,
                 (SELECT COUNT(*) FROM quiz_answers qa JOIN quizzes q
                  ON qa.quiz_id=q.id WHERE q.entry_id=e.id AND qa.correct=0)
                   AS quiz_wrong_count,
                 (SELECT COUNT(*) FROM reviews r
                  WHERE r.entry_id=e.id AND r.result='bad') AS bad_count,
                 (SELECT MAX(ts) FROM (
                    SELECT qa.ts AS ts FROM quiz_answers qa JOIN quizzes q
                      ON qa.quiz_id=q.id
                    WHERE q.entry_id=e.id AND qa.correct=0
                    UNION ALL
                    SELECT r.ts FROM reviews r
                      WHERE r.entry_id=e.id AND r.result='bad'
                  )) AS last_wrong_ts
          FROM entries e WHERE e.status='final'
        ) WHERE (quiz_wrong_count + bad_count) > 0
        """,
    ).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"], "subject": r["subject"], "submodule": r["submodule"],
            "point": r["point"], "anchor": r["anchor"], "conclusion": r["conclusion"],
            "priority": r["priority"],
            "quiz_wrong_count": r["quiz_wrong_count"],
            "bad_count": r["bad_count"],
            "wrong_count": r["quiz_wrong_count"] + r["bad_count"],
            "last_wrong_ts": r["last_wrong_ts"],
        })
    subject_rank = {s: i for i, s in enumerate(scheduler.SUBJECT_ORDER)}

    def ts_key(ts: str | None):
        if not ts:
            return (1, 0.0)
        from datetime import datetime
        return (0, -datetime.fromisoformat(ts).timestamp())

    items.sort(key=lambda it: (
        *ts_key(it["last_wrong_ts"]),
        -it["wrong_count"],
        subject_rank.get(it["subject"], len(subject_rank)),
        it["id"],
    ))
    return items[:limit]


def wrongbook_queue(conn, limit: int = 30) -> list[dict]:
    """错题重练队列：错题条目完整信息（供 FlashcardView ?queue=wrong）。"""
    wrong = wrongbook(conn, limit=500)
    ids = [w["id"] for w in wrong[:limit]]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    by_id = {}
    for r in conn.execute(
        f"SELECT * FROM entries WHERE id IN ({placeholders})", ids
    ).fetchall():
        by_id[r["id"]] = _entry_dict(r)
    items = [by_id[i] for i in ids if i in by_id]
    return review_stats.attach_reviewed_today(
        conn, review_stats.attach_read_counts(conn, items),
        date.today().isoformat(),
    )


def streak_info(conn, day: str | None = None) -> dict:
    """连续学习天数：任一模式（看/听/测）有记录即算学习日。"""
    day = day or date.today().isoformat()
    rows = conn.execute(
        "SELECT date(ts) AS d FROM reviews "
        "UNION SELECT date(ts) FROM quiz_answers"
    ).fetchall()
    active = {r["d"] for r in rows}
    current = 0
    cursor = date.fromisoformat(day)
    while cursor.isoformat() in active:
        current += 1
        cursor -= timedelta(days=1)
    longest = 0
    run = 0
    prev: date | None = None
    for d in sorted(active):
        cur = date.fromisoformat(d)
        if prev is not None and (cur - prev).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = cur
    return {"current": current, "longest": longest}


def overview(conn, days: int = 90) -> dict:
    """近 N 天日聚合（补零）+ 累计 + 掌握度 + 连胜。"""
    days = max(1, min(days, 180))
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = conn.execute(
        """
        SELECT d, read_n, listen_n, quiz_n FROM (
          SELECT date(ts) AS d,
                 SUM(CASE WHEN mode='read' THEN 1 ELSE 0 END) AS read_n,
                 SUM(CASE WHEN mode='listen' THEN 1 ELSE 0 END) AS listen_n,
                 0 AS quiz_n
          FROM reviews WHERE date(ts) >= ? GROUP BY d
          UNION ALL
          SELECT date(ts) AS d, 0 AS read_n, 0 AS listen_n, COUNT(*) AS quiz_n
          FROM quiz_answers WHERE date(ts) >= ? GROUP BY d
        ) ORDER BY d
        """,
        (start, start),
    ).fetchall()
    merged: dict[str, list[int]] = {}
    for r in rows:
        merged[r["d"]] = [r["read_n"], r["listen_n"], r["quiz_n"]]
    daily = []
    totals = {"read": 0, "listen": 0, "quiz": 0}
    for i in range(days):
        d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        read_n, listen_n, quiz_n = merged.get(d, (0, 0, 0))
        daily.append({"date": d, "read": read_n, "listen": listen_n,
                      "quiz": quiz_n})
        totals["read"] += read_n
        totals["listen"] += listen_n
        totals["quiz"] += quiz_n
    totals["minutes"] = conn.execute(
        "SELECT COALESCE(SUM(duration_sec),0) AS s FROM reviews "
        "WHERE mode='listen' AND date(ts) >= ?", (start,),
    ).fetchone()["s"] // 60
    tree = coverage_payload(conn)
    mastery = {"new": 0, "learned": 0, "weak": 0, "mastered": 0}
    for sdata in tree.values():
        for state, n in sdata["states"].items():
            mastery[state] = mastery.get(state, 0) + n
    return {"days": days, "daily": daily, "totals": totals,
            "mastery": mastery, "streak": streak_info(conn)}
