"""三级调度与动态倒排（纯函数，无 IO）。

三级规则（spec 6.2）：good→2 天后 / fuzzy→明天 / bad→明天且进错题置顶。
"""
from dataclasses import dataclass
from datetime import date

PRIORITY_ORDER = {"高频考点": 0, "易错陷阱": 1, "新增必考": 2, "普通": 3}
SUBJECT_ORDER = ("刑法", "民法", "刑诉", "民诉", "商经知", "理论法", "三国法", "行政法")


@dataclass(frozen=True)
class EntryState:
    entry_id: str
    subject: str
    submodule: str
    point: str
    priority: str
    bucket: str  # retry | review | new


def next_review_days(result: str) -> int:
    return {"good": 2, "fuzzy": 1, "bad": 1}[result]


def days_between(a: str, b: str) -> int:
    # reviews.ts 为 ISO datetime（如 2026-08-28T13:34:50），只取日期部分比较
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def classify(entry_id: str, subject: str, submodule: str, point: str,
             priority: str, last_review_ts: str | None, last_result: str | None,
             quiz_wrong_recent: bool, today: str) -> EntryState | None:
    if last_result == "bad" or quiz_wrong_recent:
        return EntryState(entry_id, subject, submodule, point, priority, "retry")
    # 听学 exposed 只记暴露不记掌握，视为未学
    if last_review_ts is None or last_result in (None, "exposed"):
        return EntryState(entry_id, subject, submodule, point, priority, "new")
    if days_between(last_review_ts, today) >= next_review_days(last_result):
        return EntryState(entry_id, subject, submodule, point, priority, "review")
    return None


def _sort_key(st: EntryState):
    subject_rank = SUBJECT_ORDER.index(st.subject) if st.subject in SUBJECT_ORDER else len(SUBJECT_ORDER)
    return (PRIORITY_ORDER[st.priority], subject_rank, st.entry_id)


def build_queue(states: list[EntryState], capacity: int,
                new_ratio: float = 0.35) -> list[str]:
    retry = sorted((s for s in states if s.bucket == "retry"), key=_sort_key)
    review = sorted((s for s in states if s.bucket == "review"), key=_sort_key)
    new = sorted((s for s in states if s.bucket == "new"), key=_sort_key)

    out = [s.entry_id for s in retry]
    remaining = capacity - len(out)
    if remaining <= 0:
        return out[:capacity]

    review_quota = min(round(remaining * (1 - new_ratio)), len(review))
    new_quota = min(remaining - review_quota, len(new))
    # 单边不足：余量给对方
    if len(review) < review_quota:
        new_quota = min(new_quota + (review_quota - len(review)), len(new))
        review_quota = len(review)
    if len(new) < new_quota:
        review_quota = min(review_quota + (new_quota - len(new)), len(review))
        new_quota = len(new)

    out += [s.entry_id for s in review[:review_quota]]
    out += [s.entry_id for s in new[:new_quota]]
    return out[:capacity]


def compute_capacity(recent: list[int], cap_max: int, default: int = 30) -> int:
    if not recent:
        return default
    avg = round(sum(recent) / len(recent))
    return max(5, min(avg, cap_max))
