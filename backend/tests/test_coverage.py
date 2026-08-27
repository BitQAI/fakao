from app import coverage as C


def test_entry_state():
    assert C.entry_state(None, 0) == "new"
    assert C.entry_state("bad", 3) == "weak"
    assert C.entry_state("good", 1) == "learned"
    assert C.entry_state("good", 2) == "mastered"


def test_coverage_tree_aggregates():
    entries = [
        {"subject": "民法", "submodule": "合同", "point": "合同效力", "state": "new"},
        {"subject": "民法", "submodule": "合同", "point": "代位权", "state": "learned"},
        {"subject": "民法", "submodule": "物权", "point": "善意取得", "state": "weak"},
    ]
    tree = C.coverage_tree(entries)
    minfa = tree["民法"]
    assert minfa["count"] == 3
    assert minfa["states"] == {"new": 1, "learned": 1, "weak": 1}
    hetong = minfa["submodules"]["合同"]
    assert hetong["points"] == {"合同效力": "new", "代位权": "learned"}
    assert hetong["count"] == 2


def test_coverage_tree_empty():
    assert C.coverage_tree([]) == {}
