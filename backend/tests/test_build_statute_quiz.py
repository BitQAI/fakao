"""法条驱动客观题脚本：依据写法与覆盖率口径。"""
from app import statute_index, statutes
from scripts import build_statute_quiz as bsq


def test_statute_basis_uses_display_name():
    """带 -全文 后缀的法条库主名不能出现在依据里，且要能反查回法条原文。"""
    law = statute_index.load_library()["民营经济促进法-全文"]
    article = law.article(41, 0)
    basis = bsq.statute_basis("民营经济促进法-全文", article)
    assert basis == "中华人民共和国民营经济促进法第四十一条"
    assert statutes.resolve_law_article(basis) == ("民营经济促进法-全文", 41, 0)


def test_statute_basis_keeps_plain_law_names():
    law = statute_index.load_library()["中华人民共和国刑法"]
    article = law.article(269, 0)
    assert bsq.statute_basis("中华人民共和国刑法", article) == \
        "中华人民共和国刑法第二百六十九条"
