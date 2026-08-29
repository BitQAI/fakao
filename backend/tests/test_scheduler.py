from app import scheduler as S


def test_next_review_days():
    assert S.next_review_days("good") == 2
    assert S.next_review_days("fuzzy") == 1
    assert S.next_review_days("bad") == 1


def test_days_between():
    assert S.days_between("2026-08-25", "2026-08-27") == 2


def test_days_between_accepts_datetime_ts():
    assert S.days_between("2026-08-26T10:00:00", "2026-08-28") == 2


def test_classify_buckets():
    today = "2026-08-27"
    assert S.classify("XF-001", "刑法", "分则-财产犯罪", "转化型抢劫", "高频考点",
                      "2026-08-27", "bad", False, today).bucket == "retry"
    assert S.classify("XF-001", "刑法", "分则-财产犯罪", "转化型抢劫", "高频考点",
                      "2026-08-27", "good", True, today).bucket == "retry"
    assert S.classify("XF-001", "刑法", "分则-财产犯罪", "转化型抢劫", "高频考点",
                      None, None, False, today).bucket == "new"
    assert S.classify("XF-001", "刑法", "分则-财产犯罪", "转化型抢劫", "高频考点",
                      "2026-08-25", "good", False, today).bucket == "review"
    assert S.classify("XF-001", "刑法", "分则-财产犯罪", "转化型抢劫", "高频考点",
                      "2026-08-27", "good", False, today) is None


def test_classify_exposed_treated_as_new():
    st = S.classify("XF-001", "刑法", "a", "p", "高频考点",
                    "2026-08-26T10:00:00", "exposed", False, "2026-08-28")
    assert st is not None and st.bucket == "new"


def test_build_queue_retry_first_then_quota():
    states = [
        S.EntryState("XF-001", "刑法", "a", "p1", "高频考点", "retry"),
        S.EntryState("XF-002", "刑法", "a", "p2", "高频考点", "review"),
        S.EntryState("XF-003", "刑法", "a", "p3", "易错陷阱", "review"),
        S.EntryState("XF-004", "刑法", "a", "p4", "高频考点", "new"),
        S.EntryState("XF-005", "刑法", "a", "p5", "普通", "new"),
    ]
    queue = S.build_queue(states, capacity=4, new_ratio=0.5)
    assert queue[0] == "XF-001"          # retry 最前
    assert queue[1] == "XF-002"          # review 按优先级
    assert queue[2] == "XF-003"
    assert queue[3] == "XF-004"          # 余量给 new
    assert len(queue) == 4


def test_build_queue_single_side_shortfall():
    states = [
        S.EntryState("XF-001", "刑法", "a", "p1", "高频考点", "retry"),
        S.EntryState("XF-002", "刑法", "a", "p2", "高频考点", "new"),
    ]
    # review 为空，余量应全给 new
    assert S.build_queue(states, capacity=2, new_ratio=0.1) == ["XF-001", "XF-002"]


def test_build_queue_truncates_capacity():
    states = [S.EntryState(f"XF-{i:03d}", "刑法", "a", f"p{i}", "普通", "new")
              for i in range(1, 6)]
    assert len(S.build_queue(states, capacity=3, new_ratio=0.5)) == 3


def test_build_queue_orders_by_priority_then_subject():
    states = [
        S.EntryState("MF-001", "民法", "a", "p1", "高频考点", "new"),
        S.EntryState("LL-001", "理论法", "a", "p2", "高频考点", "new"),
        S.EntryState("XS-001", "刑诉", "a", "p3", "普通", "new"),
        S.EntryState("XF-001", "刑法", "a", "p4", "易错陷阱", "new"),
    ]
    queue = S.build_queue(states, capacity=4, new_ratio=1.0)
    # 高频考点优先（刑法规前），易错陷阱次之，普通最后
    assert queue == ["MF-001", "LL-001", "XF-001", "XS-001"]


def test_compute_capacity():
    assert S.compute_capacity([], cap_max=50) == 30
    assert S.compute_capacity([40, 50, 60], cap_max=50) == 50
    assert S.compute_capacity([1, 2, 3], cap_max=50) == 5
