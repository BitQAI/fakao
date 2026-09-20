"""主观题模板层测试：题型 → 骨架 / 维度 / 卷面题号 / 形式要求。"""
from app import subjective_templates as stpl


def test_case_skeleton_keeps_subject_specific_route():
    assert any("请求权基础" in s for s in stpl.skeleton_for("民法"))
    assert any("共同犯罪" in s for s in stpl.skeleton_for("刑法"))


def test_essay_skeleton_by_qtype():
    assert stpl.skeleton_for("理论法", "essay") == stpl.ESSAY_SKELETON
    # 论述题骨架与科目无关：民法也要走四段式
    assert any("总论点" in s for s in stpl.skeleton_for("民法", "essay"))


def test_composite_skeleton_is_cross_subject():
    skeleton = stpl.skeleton_for("民法", "composite")
    assert skeleton == stpl.COMPOSITE_SKELETON
    joined = "".join(skeleton)
    for term in ("请求权", "管辖", "商法"):
        assert term in joined


def test_kinds_are_separate_sets():
    assert stpl.kinds_for("essay") == stpl.ESSAY_KINDS
    assert stpl.kinds_for("case") == stpl.POINT_KINDS
    assert stpl.kinds_for("composite") == stpl.POINT_KINDS
    assert not set(stpl.POINT_KINDS) & set(stpl.ESSAY_KINDS)


def test_kind_order_covers_both_sets():
    assert set(stpl.kind_order()) == set(stpl.POINT_KINDS) | set(stpl.ESSAY_KINDS)


def test_slot_for_composite_is_question_four():
    slot = stpl.slot_for("民法", "composite")
    assert slot["slot"] == 4 and slot["score"] == 55 and slot["minutes"] == 70


def test_slot_for_essay_ignores_subject():
    slot = stpl.slot_for("", "essay")
    assert slot["slot"] == 1 and slot["score"] == 35


def test_spec_falls_back_to_case():
    assert stpl.spec_for("nonsense") == stpl.SPECS["case"]
    assert stpl.spec_for("essay")["min_chars"] == 600
    assert stpl.spec_for("composite")["min_questions"] == 8


def test_squash_strips_punctuation_and_space():
    assert stpl.squash("民法，第 172 条。") == "民法第172条"
    assert stpl.squash(None) == ""
