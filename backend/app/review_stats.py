"""看/听历史与合并排行榜统计（基于 reviews 表的聚合查询）。"""
from datetime import date


def attach_read_counts(conn, items: list[dict]) -> list[dict]:
    """批量给条目附加 read_count（看背卡片显示已看次数）。"""
    if not items:
        return items
    ids = [it["id"] for it in items]
    placeholders = ",".join("?" * len(ids))
    counts = {r["entry_id"]: r["n"] for r in conn.execute(
        f"SELECT entry_id, COUNT(*) AS n FROM reviews "
        f"WHERE mode='read' AND entry_id IN ({placeholders}) GROUP BY entry_id",
        ids)}
    for it in items:
        it["read_count"] = counts.get(it["id"], 0)
    return items


def attach_reviewed_today(conn, items: list[dict],
                          day: str | None = None) -> list[dict]:
    """批量标记条目今天是否已看过（看背进度记忆）。"""
    if not items:
        return items
    day = day or date.today().isoformat()
    ids = [it["id"] for it in items]
    placeholders = ",".join("?" * len(ids))
    done = {r["entry_id"] for r in conn.execute(
        f"SELECT DISTINCT entry_id FROM reviews "
        f"WHERE mode='read' AND date(ts)=? AND entry_id IN ({placeholders})",
        [day, *ids])}
    for it in items:
        it["reviewed_today"] = it["id"] in done
    return items


def attach_listen_counts(conn, items: list[dict]) -> list[dict]:
    """批量给条目附加 listen_count / last_ts（听学队列与自定义范围标记已听）。"""
    if not items:
        return items
    ids = [it["id"] for it in items]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT entry_id, COUNT(*) AS n, MAX(ts) AS last_ts FROM reviews "
        f"WHERE mode='listen' AND entry_id IN ({placeholders}) GROUP BY entry_id",
        ids).fetchall()
    by_id = {r["entry_id"]: r for r in rows}
    for it in items:
        r = by_id.get(it["id"])
        it["listen_count"] = r["n"] if r else 0
        it["last_ts"] = r["last_ts"] if r else None
    return items


def attach_listened_today(conn, items: list[dict],
                          day: str | None = None) -> list[dict]:
    """批量标记条目今天是否已听过（听背进度记忆，对标 attach_reviewed_today）。"""
    if not items:
        return items
    day = day or date.today().isoformat()
    ids = [it["id"] for it in items]
    placeholders = ",".join("?" * len(ids))
    done = {r["entry_id"] for r in conn.execute(
        f"SELECT DISTINCT entry_id FROM reviews "
        f"WHERE mode='listen' AND date(ts)=? AND entry_id IN ({placeholders})",
        [day, *ids])}
    for it in items:
        it["listened_today"] = it["id"] in done
    return items


def review_history(conn, limit: int = 100,
                   mode: str | None = None) -> list[dict]:
    """看/听历史：reviews JOIN entries，按时间倒序。"""
    sql = """
        SELECT r.id, r.entry_id, r.ts, r.mode, r.result, r.duration_sec,
               e.subject, e.submodule, e.point, e.anchor, e.conclusion, e.priority
        FROM reviews r JOIN entries e ON e.id = r.entry_id
    """
    params: list = []
    if mode in ("read", "listen"):
        sql += " WHERE r.mode = ?"
        params.append(mode)
    sql += " ORDER BY r.ts DESC, r.id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [{
        "id": r["id"], "entry_id": r["entry_id"], "ts": r["ts"],
        "mode": r["mode"], "result": r["result"],
        "duration_sec": r["duration_sec"],
        "entry": {
            "id": r["entry_id"], "subject": r["subject"],
            "submodule": r["submodule"], "point": r["point"],
            "anchor": r["anchor"], "conclusion": r["conclusion"],
            "priority": r["priority"],
        },
    } for r in rows]


def leaderboard(conn, limit: int = 200, sort: str = "total") -> list[dict]:
    """看+听合并统计：按条目聚合次数、重复次数、最近时间。"""
    rows = conn.execute(
        """
        SELECT e.id, e.subject, e.submodule, e.point, e.anchor,
               e.conclusion, e.priority,
               COALESCE(SUM(CASE WHEN r.mode='read' THEN 1 ELSE 0 END), 0)
                 AS read_count,
               COALESCE(SUM(CASE WHEN r.mode='listen' THEN 1 ELSE 0 END), 0)
                 AS listen_count,
               COUNT(r.id) AS total_count,
               MAX(r.ts) AS last_ts
        FROM entries e LEFT JOIN reviews r ON r.entry_id = e.id
        WHERE e.status = 'final'
        GROUP BY e.id
        """
    ).fetchall()
    items = []
    for r in rows:
        rc, lc = r["read_count"], r["listen_count"]
        if rc + lc == 0:
            continue  # 只含有学习记录的条目
        items.append({
            "entry_id": r["id"], "subject": r["subject"],
            "submodule": r["submodule"], "point": r["point"],
            "anchor": r["anchor"], "conclusion": r["conclusion"],
            "priority": r["priority"],
            "read_count": rc, "listen_count": lc, "total_count": rc + lc,
            "read_repeat": max(rc - 1, 0), "listen_repeat": max(lc - 1, 0),
            "last_ts": r["last_ts"],
        })
    sort_key = {"total": "total_count", "read": "read_count",
                "listen": "listen_count"}.get(sort, "total_count")
    items.sort(key=lambda it: (-it[sort_key], it["entry_id"]))
    return items[:limit]
