from app import number_terms as nt


def test_chinese_to_int():
    assert nt.chinese_to_int("十") == 10
    assert nt.chinese_to_int("十五") == 15
    assert nt.chinese_to_int("二十") == 20
    assert nt.chinese_to_int("三十七") == 37
    assert nt.chinese_to_int("一百") == 100
    assert nt.chinese_to_int("一千二百") == 1200
    assert nt.chinese_to_int("十万") == 100000
    assert nt.chinese_to_int("30") == 30
    assert nt.chinese_to_int("甲") is None


def test_extract_terms():
    nums = nt.extract("处五年以下有期徒刑，并处二万元以上二十万元以下罚金。")
    assert (5.0, "年", "以下") in nums
    assert (20000.0, "元", "以上") in nums
    assert (200000.0, "元", "以下") in nums


def test_extract_ignores_article_no_and_year():
    nums = nt.extract("依据刑事诉讼法第91条，2018年修正后拘留期限为37日。")
    assert (91.0, "条", "") not in nums          # 条目号不算考点
    assert nums == {(37.0, "日", "")}


def test_fabricated_detects_mutated_number():
    article = "人民法院应当在收到起诉状之日起七日内决定是否立案。"
    right = "人民法院应当在收到起诉状之日起七日内决定是否立案。"
    wrong = "人民法院应当在收到起诉状之日起十五日内决定是否立案。"
    assert nt.fabricated(right, article) == set()
    assert nt.fabricated(wrong, article) == {(15.0, "日", "")}


def test_is_grounded_true_question_must_not_invent_numbers():
    article = "商业银行的注册资本最低限额为十亿元人民币。"
    ok, _ = nt.is_grounded("商业银行注册资本最低限额为十亿元人民币。", article, "对")
    assert ok
    bad, why = nt.is_grounded("商业银行注册资本最低限额为二十亿元人民币。", article, "对")
    assert not bad and "原文外" in why


def test_is_grounded_false_question_needs_one_mutation():
    article = "拘役的期限为一个月以上六个月以下。"
    ok, _ = nt.is_grounded("拘役的期限为一个月以上九个月以下。", article, "错")
    assert ok
    bad, why = nt.is_grounded("拘役的期限为一个月以上六个月以下。", article, "错")
    assert not bad and "未改写" in why
    too_many, why2 = nt.is_grounded("管制期限为九个月以上十二个月以下。", article, "错")
    assert not too_many and "上限" in why2


def test_yinei_and_nei_are_equivalent():
    """「三日以内」与「三日内」同义，不能算作改写。"""
    ref = "公安机关应当在拘留后的三日以内提请人民检察院审查批准。"
    assert nt.extract(ref) == {(3.0, "日", "")}
    assert nt.fabricated("公安机关应在拘留后三日内提请批准逮捕。", ref) == set()


def test_is_grounded_requires_numbers_in_stem():
    ok, why = nt.is_grounded("法院应当立案。", "人民法院应当立案。", "对")
    assert not ok and "无数字" in why


def test_percent_and_unit_forms():
    article = "股东会作出决议须经代表三分之二以上表决权的股东通过。"
    assert nt.extract("三分之二") == {(0.6667, "比例", "")}   # 分数（法律高频）
    assert nt.extract("百分之十") == {(10.0, "%", "")}
    assert nt.extract("持股比例 30%以上") == {(30.0, "%", "以上")}
    assert nt.fabricated("持股 50%以上", article) == {(50.0, "%", "以上")}


def test_fraction_mismatch_is_detected():
    ref = "董事会决议须经三分之二以上董事通过。"
    assert nt.fabricated("董事会决议须经四分之三以上董事通过。", ref) == \
        {(0.75, "比例", "")}
    assert nt.fabricated("董事会决议须经三分之二以上董事通过。", ref) == set()
    # 人数 / 期限同样覆盖
    assert nt.extract("仲裁委员会由主任一人、副主任四人和委员十一人组成") == \
        {(1.0, "人", ""), (4.0, "人", ""), (11.0, "人", "")}
