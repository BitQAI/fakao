"""关系词闸门单测：对题禁新增、错题限白名单单点偷换。"""
from app import relation_terms as rt


def test_extract_prefers_longer_terms():
    terms = rt.terms_of("二审法院发回重审的，应当另行组成合议庭。")
    assert "发回重审" in terms
    assert "重审" not in terms          # 被更长的「发回重审」吃掉
    assert {"二审", "应当", "合议庭"} <= terms


def test_extract_drops_contained_short_term():
    terms = rt.terms_of("当事人撤回起诉的，可以再次起诉。")
    assert "撤回起诉" in terms
    assert "撤回" not in terms          # 被「撤回起诉」包含，不再单独计
    assert "撤诉" not in terms


def test_families_of_sorted_by_rarity():
    fams = rt.families_of("合议庭认为应当追加当事人的，可以撤销原判。")
    assert fams.index("org") < fams.index("effect") < fams.index("modal")


def test_subject_terms_ignores_generic_words():
    assert rt.subject_terms("由委员会讨论决定") == set()
    assert rt.subject_terms("上一级人民法院批准") == {"人民法院"}


def test_true_question_passes_when_terms_covered():
    article = "人民法院审理民事案件，应当在开庭三日前通知当事人。"
    stem = "法院开庭前应当通知当事人。"
    ok, _ = rt.check(stem, article, "对")
    assert ok


def test_true_question_rejects_new_relation_term():
    article = "人民法院审理民事案件，应当在开庭三日前通知当事人。"
    stem = "法院可以不开庭直接通知当事人。"
    ok, why = rt.check(stem, article, "对")
    assert not ok and "可以" in why


def test_true_question_rejects_change_of_decision_to_resolution():
    article = "股东会作出决议，应当经代表三分之二以上表决权的股东通过。"
    stem = "该事项由股东会作出决定即可。"
    ok, why = rt.check(stem, article, "对")
    assert not ok and "决定" in why


def test_false_question_passes_on_whitelisted_swap():
    article = "适用简易程序审理的民事案件，由审判员一人独任审理。"
    stem = "适用简易程序审理的民事案件，由合议庭审理。"
    ok, why = rt.check(stem, article, "错")
    assert ok, why


def test_false_question_rejects_two_changes():
    article = "人民法院对不予受理的裁定，当事人可以提起上诉。"
    stem = "人民检察院对驳回起诉的裁定，当事人应当提起抗诉。"
    ok, why = rt.check(stem, article, "错")
    assert not ok and "上限" in why


def test_false_question_rejects_off_whitelist_swap():
    article = "人民法院审理民事案件，应当在开庭三日前通知当事人。"
    stem = "人民法院审理民事案件，撤销开庭通知当事人。"
    ok, why = rt.check(stem, article, "错")
    assert not ok


def test_false_question_requires_a_swap():
    article = "人民法院审理民事案件，应当在开庭三日前通知当事人。"
    stem = "人民法院审理民事案件，应当通知当事人。"
    ok, why = rt.check(stem, article, "错")
    assert not ok and "未偷换" in why


def test_swap_first_instance_to_second_instance():
    article = "当事人不服一审判决的，有权提起上诉。"
    stem = "当事人不服二审判决的，有权提起上诉。"
    ok, why = rt.check(stem, article, "错")
    assert ok, why


def test_swap_reconsideration_to_review():
    article = "对行政复议决定不服的，可以提起行政诉讼。"
    stem = "对行政复核决定不服的，可以提起行政诉讼。"
    ok, why = rt.check(stem, article, "错")
    assert ok, why


def test_swap_judgment_to_ruling():
    article = "人民法院对管辖权异议，应当作出裁定。"
    stem = "人民法院对管辖权异议，应当作出判决。"
    ok, why = rt.check(stem, article, "错")
    assert ok, why


def test_fine_to_penalty_direction():
    article = "对单位违反规定的，处十万元罚款。"
    stem = "对单位违反规定的，判处罚金。"
    ok, why = rt.check(stem, article, "错")
    assert ok, why


def test_swap_level_upward_to_same_level():
    article = "应当报请上一级人民法院批准。"
    stem = "应当报请本级人民法院批准。"
    ok, why = rt.check(stem, article, "错")
    assert ok, why


def test_subject_must_match_reference():
    article = "人民法院应当在收到起诉状之日起七日内立案。"
    stem = "人民检察院应当立即审查是否立案。"
    ok, why = rt.check(stem, article, "对")
    assert not ok and "主体" in why


def test_true_question_that_copies_article_is_rejected():
    article = "权利人向义务人提出履行请求的，诉讼时效中断，从中断时起重新计算。"
    stem = "权利人向义务人提出履行请求的，诉讼时效中断，从中断时起重新计算。"
    ok, why = rt.check(stem, article, "对")
    assert not ok and "抄原文" in why


def test_stem_without_relation_term_is_rejected():
    article = "本法的施行日期由国务院规定。"
    stem = "本法的施行日期另行规定。"
    ok, why = rt.check(stem, article, "对")
    assert not ok and "无关系词" in why


def test_answer_must_be_judge_values():
    ok, why = rt.check("应当立案", "应当立案审理", "maybe")
    assert not ok and "对" in why


def test_swap_table_terms_exist_in_families():
    vocabulary = {term for terms in rt.FAMILIES.values() for term in terms}
    assert set(rt.SWAPS) <= vocabulary
    for targets in rt.SWAPS.values():
        assert set(targets) <= vocabulary


def test_family_order_covers_all_families():
    assert set(rt.FAMILY_ORDER) == set(rt.FAMILIES)
