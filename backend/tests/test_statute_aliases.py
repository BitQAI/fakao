"""法条别名与解析回归测试。

目的：把「别名指错文件」「条号被正则误吃」这类静默失效变成显式失败。
"""
import pytest

from app import statute_index as si
from app import statutes


def test_all_aliases_point_to_existing_files():
    """别名表里每一项都必须能在 data/法条库 找到对应文件。"""
    missing = [a for a in statutes.STATUTE_ALIASES
               if statutes.resolve_law_file(a) is None]
    assert missing == []


@pytest.mark.parametrize("ref,expect", [
    ("民诉解释304条", "申请执行人"),
    ("公司法解释三14条", "抽逃出资"),
    ("担保制度解释62条", "留置"),
    ("破产法41条", "破产费用"),
    ("证据规定第5条", "委托诉讼代理人"),
    ("公司法（2023）第47条", "注册资本"),
    ("民法典总则编解释28条", "相对人"),
    ("刑诉法解释第124条", "刑讯逼供"),
    ("高法解释432条", "死刑"),
    ("刑法287条之二", "信息网络"),
    ("民法典第1165条", "过错"),
    ("证券法19条", "披露"),
])
def test_representative_refs_resolve(ref, expect):
    body = statutes.resolve_statute(ref)
    assert body, f"{ref} 未能解析"
    assert expect in body, f"{ref} 解析到意外条文：{body[:60]}"


def test_qualifier_suffix_stripped():
    assert statutes.resolve_law_file("公司法（2023）") is not None
    assert statutes.resolve_law_file("民事诉讼法（2023修正）") is not None
    assert statutes.resolve_law_file("公司法（2023）") == statutes.resolve_law_file("公司法")


def test_mixed_numeral_not_swallowed():
    """「公司法解释三14条」不能被贪婪吃成 num=「三14」。"""
    m = statutes._ARTICLE_RE.search("公司法解释三14条")
    assert m is not None
    assert m.group("num") == "14"
    assert "公司法解释三14条"[:m.start()] == "公司法解释三"


def test_library_parses():
    """全量法条库可解析；仅修正案与立法解释类非条文式文本允许 0 条。"""
    lib = si.load_library()
    assert len(lib) >= 55
    allowed_empty = {
        "中华人民共和国刑法修正案（十二）",
        "全国人民代表大会常务委员会关于《中华人民共和国刑事诉讼法》第二百九十二条的解释",
    }
    empty = {k for k, law in lib.items() if not law.articles}
    assert empty <= allowed_empty
    assert sum(len(law.articles) for law in lib.values()) >= 7000
