"""覆盖树聚合（纯函数）：科目 → 子科目 → 考点，按学习状态着色。

状态口径与 scheduler 对齐（spec 2026-08-31）：
- new 未学：无 read/listen/quiz 任何记录
- weak 薄弱：命中 retry 桶（最近 result=bad 或 quiz 曾答错）
- mastered 掌握：最近 result=good 且 read 次数 >= 2
- learned 已学：其余有记录
"""


def entry_state(last_result: str | None, review_count: int,
                quiz_wrong: bool = False,
                has_record: bool | None = None) -> str:
    if has_record is None:
        has_record = last_result is not None or review_count > 0
    if not has_record:
        return "new"
    if quiz_wrong or last_result == "bad":
        return "weak"
    if last_result == "good" and review_count >= 2:
        return "mastered"
    return "learned"


def _merge(target: dict, state: str, unread: bool = False,
           unlistened: bool = False) -> None:
    target["count"] += 1
    target["states"][state] = target["states"].get(state, 0) + 1
    if unread:
        target["unread"] += 1
    if unlistened:
        target["unlistened"] += 1


def coverage_tree(entries: list[dict]) -> dict:
    tree = {}
    for e in entries:
        unread = bool(e.get("unread", False))
        unlistened = bool(e.get("unlistened", False))
        subject = tree.setdefault(
            e["subject"],
            {"count": 0, "states": {}, "unread": 0, "unlistened": 0,
             "submodules": {}},
        )
        sub = subject["submodules"].setdefault(
            e["submodule"],
            {"count": 0, "states": {}, "unread": 0, "unlistened": 0,
             "points": {}},
        )
        _merge(subject, e["state"], unread, unlistened)
        _merge(sub, e["state"], unread, unlistened)
        # 同一子模块下 point 名可能重复：state 取最后一条，计数累加
        pt = sub["points"].setdefault(
            e["point"], {"state": e["state"], "unread": 0, "unlistened": 0})
        pt["state"] = e["state"]
        if unread:
            pt["unread"] += 1
        if unlistened:
            pt["unlistened"] += 1
    return tree
