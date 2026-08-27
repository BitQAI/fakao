"""覆盖树聚合（纯函数）：科目 → 子科目 → 考点，按学习状态着色。"""


def entry_state(last_result: str | None, review_count: int) -> str:
    if last_result is None:
        return "new"
    if last_result == "bad":
        return "weak"
    if last_result == "good" and review_count >= 2:
        return "mastered"
    return "learned"


def _merge(target: dict, state: str) -> None:
    target["count"] += 1
    target["states"][state] = target["states"].get(state, 0) + 1


def coverage_tree(entries: list[dict]) -> dict:
    tree = {}
    for e in entries:
        subject = tree.setdefault(
            e["subject"],
            {"count": 0, "states": {}, "submodules": {}},
        )
        sub = subject["submodules"].setdefault(
            e["submodule"],
            {"count": 0, "states": {}, "points": {}},
        )
        _merge(subject, e["state"])
        _merge(sub, e["state"])
        sub["points"][e["point"]] = e["state"]
    return tree
