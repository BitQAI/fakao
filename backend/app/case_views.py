"""案例阅读记录（看过标记 + 阅读历史，只写 case_views 一张表）。

单用户本地库：一条案例一行，`views` 计次、`last_viewed_at` 即历史排序键。
检索侧的「未看过优先 / 只看未看过」由 case_index 读取本模块的 `viewed_keys`。
"""
from __future__ import annotations

from datetime import datetime

#: 阅读状态筛选：全部 / 未看过 / 已看过
VIEWED_FILTERS = ("", "no", "yes")

#: 历史条目 JOIN cases 取的字段（标题等信息不冗余存进阅读记录）
_HIST_COLS = ("v.source, v.loc, v.first_viewed_at, v.last_viewed_at, v.views, "
              "c.title, c.category, c.case_no, c.date, c.url")


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def mark_viewed(conn, source: str, loc: str) -> dict:
    """打点一篇案例：首次写入，之后只刷新 last_viewed_at 与 views。"""
    now = _now()
    conn.execute(
        "INSERT INTO case_views (source, loc, first_viewed_at, last_viewed_at, views) "
        "VALUES (?,?,?,?,1) "
        "ON CONFLICT(source, loc) DO UPDATE SET "
        "last_viewed_at=excluded.last_viewed_at, views=views+1",
        (source, loc, now, now))
    conn.commit()
    row = conn.execute(
        "SELECT source, loc, first_viewed_at, last_viewed_at, views FROM case_views "
        "WHERE source=? AND loc=?", (source, loc)).fetchone()
    out = dict(row)
    out["first_time"] = out["views"] == 1
    return out


def viewed_keys(conn) -> set[tuple[str, str]]:
    """全部已看过案例的 (source, loc)；用于列表标识、排序与筛选。"""
    return {(r["source"], r["loc"]) for r in conn.execute(
        "SELECT source, loc FROM case_views").fetchall()}


def is_viewed(conn, source: str, loc: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM case_views WHERE source=? AND loc=?",
        (source, loc)).fetchone() is not None


def history(conn, limit: int = 30) -> dict:
    """最近看过的案例（按 last_viewed_at 倒序）；已从案例库移除的记录不返回。"""
    rows = conn.execute(
        f"SELECT {_HIST_COLS} FROM case_views v JOIN cases c "
        "ON c.source=v.source AND c.loc=v.loc "
        "ORDER BY v.last_viewed_at DESC, v.source, v.loc LIMIT ?",
        (limit,)).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM case_views v JOIN cases c "
        "ON c.source=v.source AND c.loc=v.loc").fetchone()["n"]
    return {"items": [dict(r) for r in rows], "total": total}


def previous_view(conn, source: str, loc: str) -> dict | None:
    """阅读轨迹上的「上一篇」：比当前篇更早打开的那一篇。

    当前篇尚未打点（首次打开）时取「最近看过的一篇」。同一毫秒的并列回退到
    last_viewed_at 再比 (source, loc)，保证每次都返回确定的一篇。
    """
    row = conn.execute(
        "SELECT last_viewed_at FROM case_views WHERE source=? AND loc=?",
        (source, loc)).fetchone()
    if row is None:
        return _join_case(conn, "ORDER BY v.last_viewed_at DESC, v.source, v.loc")
    return _join_case(
        conn, "WHERE v.last_viewed_at <= ? AND NOT (v.source=? AND v.loc=?) "
        "ORDER BY v.last_viewed_at DESC, v.source, v.loc",
        (row["last_viewed_at"], source, loc))


def _join_case(conn, tail: str, params: tuple = ()) -> dict | None:
    """轨迹查询：阅读记录 JOIN cases（悬空记录自然被过滤），只回导航需要的字段。"""
    row = conn.execute(
        f"SELECT {_HIST_COLS} FROM case_views v JOIN cases c "
        f"ON c.source=v.source AND c.loc=v.loc {tail} LIMIT 1", params).fetchone()
    return dict(row) if row else None


def clear(conn) -> int:
    """清空阅读记录（「看过」标记与历史一起重置）。"""
    n = conn.execute("DELETE FROM case_views").rowcount
    conn.commit()
    return n
