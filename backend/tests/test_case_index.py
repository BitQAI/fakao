"""案例库检索与文书化分节测试。"""
import json

import pytest

from app import case_index, case_views, db
from app.cases import CASE_SOURCES

JCY_TEXT = """（检例第39号）
【关键词】
操纵证券市场 “抢帽子”交易 公开荐股
【要旨】
证券公司及其工作人员违背从业禁止规定，情节严重的，以操纵证券市场罪追究其刑事责任。
【基本案情】
被告人朱炜明系证券经纪人。
【相关规定】
《中华人民共和国刑法》第一百八十二条
周辉集资诈骗案
"""

ZGFY_TEXT = """# 指导性案例第1号：上海中原物业顾问有限公司诉陶德华居间合同纠纷案
（发布批次：第1批　发布日期：2012-01-11）
指导案例1号
（最高人民法院审判委员会讨论通过 2011年12月20日发布）
关键词　民事　居间合同　违约
裁判要点
买方未利用中介公司提供的信息而通过其他正当途径获得房源信息的，不构成违约。
基本案情
法院经审理查明：原产权人通过多家中介公司挂牌出售同一房屋。
裁判理由
衡量是否“跳单”违约的关键，是看买方是否利用了该中介公司提供的信息。
裁判结果
一、撤销一审判决；二、驳回中原公司的诉讼请求。
"""

RMFY_TEXT = """1.承租人擅自变动房屋建筑主体或承重结构，出租人请求赔偿相关费用的，应予支持。
2.承租人拒不协助删除网络地图标注的，出租人请求其协助删除的，应予支持。
银某南通分公司承租案涉房屋后对房屋进行了装修改造。
银某南通分公司承租案涉房屋后对房屋进行了装修改造。
租赁合同到期后银某南通分公司表示不再续租。
"""


def _seed(conn, rows):
    conn.executemany(
        "INSERT INTO cases (source, loc, title, category, case_no, keywords, date, "
        "url, text) VALUES (?,?,?,?,?,?,?,?,?)",
        [(*r[:5], json.dumps(r[5], ensure_ascii=False), r[6], r[7], r[8]) for r in rows])
    conn.commit()


@pytest.fixture()
def conn(tmp_db):
    db_path, _ = tmp_db
    return db.connect(db_path)


def test_sections_bracket_and_leaked_tail():
    out, dropped = case_index.sections(JCY_TEXT)
    # 相关法条类小节前置到案情之前（阅读顺序优化）
    assert [s["label"] for s in out] == ["关键词", "要旨", "相关规定", "基本案情"]
    law = next(s for s in out if s["label"] == "相关规定")
    assert "第一百八十二条" in law["text"]
    assert all("周辉集资诈骗案" not in s["text"] for s in out)
    assert dropped == 0


def test_sections_bare_headers_drop_preamble():
    out, _dropped = case_index.sections(ZGFY_TEXT)
    labels = [s["label"] for s in out]
    assert labels == ["关键词", "裁判要点", "基本案情", "裁判理由", "裁判结果"]
    assert all("指导性案例第1号" not in s["text"] for s in out)
    assert all("发布批次" not in s["text"] for s in out)


def test_sections_numbered_summary_lifted():
    out, _dropped = case_index.sections(RMFY_TEXT)
    assert out[0]["label"] == "裁判要旨"
    assert out[0]["text"].count("\n") == 1  # 两条要旨
    assert out[1]["label"] == ""
    assert "租赁合同到期后" in out[1]["text"]


def test_sections_drops_consecutive_duplicate():
    out, dropped = case_index.sections(RMFY_TEXT)
    assert dropped == 1
    assert out[1]["text"].count("银某南通分公司承租案涉房屋后对房屋进行了装修改造") == 1


def test_sections_empty_text():
    assert case_index.sections("") == ([], 0)


RMFY_FOOTER_TEXT = """1.承租人对房屋恢复原状负有义务。
法院于2023年4月7日作出判决，驳回诉讼请求。宣判后，当事人提起上诉。法院于2023年8月29日作出判决，驳回上诉。　　法院于2023年4月7日作出判决，驳回诉讼请求。宣判后，当事人提起上诉。法院于2023年8月29日作出判决，驳回上诉。　　本案的争议焦点是责任如何承担。
######　　一审：上海金融法院（2022）沪74行初2号行政判决（2023年4月7日）
二审：上海市高级人民法院（2022）沪行终115号行政判决（2023年8月29日）
《中华人民共和国银行业监督管理法》第21条、第48条
---
下一篇案例标题
"""


def test_sections_pull_footer_law_and_procedure():
    out, dropped = case_index.sections(RMFY_FOOTER_TEXT)
    labels = [s["label"] for s in out]
    assert labels == ["裁判要旨", "相关法条", "", "审理程序"]
    proc = next(s for s in out if s["label"] == "审理程序")
    assert proc["text"].startswith("一审：上海金融法院")
    assert proc["text"].count("\n") == 1
    law = next(s for s in out if s["label"] == "相关法条")
    assert law["text"].startswith("《中华人民共和国银行业监督管理法》")
    assert "下一篇案例标题" not in "".join(s["text"] for s in out)
    assert dropped == 3  # 句子块被判词重复 3 句


def test_sections_drop_repeated_sentence_run():
    text = ("法院于2023年4月7日作出判决，驳回诉讼请求。宣判后提起上诉。"
            "法院于2023年8月29日作出判决，驳回上诉。"
            "法院于2023年4月7日作出判决，驳回诉讼请求。宣判后提起上诉。"
            "法院于2023年8月29日作出判决，驳回上诉。")
    out, dropped = case_index.sections(text)
    assert dropped == 3
    assert out[0]["text"].count("驳回上诉") == 1


def test_search_multi_term_is_and(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "房屋租赁合同纠纷案", "参考案例",
         "（2018）苏06民终4610号", ["民事", "房屋租赁"], "2019.02.26", "",
         "承租人擅自变动房屋建筑主体，出租人请求赔偿。"),
        ("人民法院案例库", "case_2", "房屋买卖合同纠纷案", "参考案例", "",
         ["民事"], "2020.01.01", "", "买方跳单违约。"),
    ])
    out = case_index.search(conn, "房屋 租赁")
    assert [h["loc"] for h in out["items"]] == ["case_1"]
    assert out["total"] == 1


def test_search_title_hit_ranks_first(conn):
    _seed(conn, [
        ("人民法院案例库", "case_a", "买卖合同纠纷案", "参考案例", "", [],
         "2021.01.01", "", "正文里提到居间合同与跳单。"),
        ("人民法院案例库", "case_b", "居间合同跳单案", "参考案例", "", [],
         "2020.01.01", "", "正文无关。"),
    ])
    hits = case_index.search(conn, "居间合同")["items"]
    assert [h["loc"] for h in hits] == ["case_b", "case_a"]
    assert hits[0]["score"] > hits[1]["score"]
    assert "居间合同" in hits[1]["snippet"]  # 正文命中处居中截取


def test_search_source_filter_and_limit(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲诉乙租赁案", "参考案例", "", [],
         "2019.01.01", "", "租赁纠纷。"),
        ("司法部案例库", "case_2", "丙与丁租赁调解案", "调解", "", [],
         "2020.01.01", "", "租赁纠纷。"),
        ("司法部案例库", "case_3", "戊与己租赁调解案", "调解", "", [],
         "2021.01.01", "", "租赁纠纷。"),
    ])
    assert case_index.search(conn, "租赁")["total"] == 3
    hits = case_index.search(conn, "租赁", source="司法部案例库")["items"]
    assert {h["loc"] for h in hits} == {"case_2", "case_3"}
    one = case_index.search(conn, "租赁", limit=1)
    assert len(one["items"]) == 1 and one["total"] == 3  # total 是全量命中数


def test_browse_without_query_returns_list(conn):
    """空 q 是浏览模式：按日期倒序返回，不是空结果。"""
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲案", "参考案例", "", ["民事"], "2019.01.01", "", "旧案正文。"),
        ("人民法院案例库", "case_2", "乙案", "参考案例", "", ["民事"], "2024.01.01", "", "新案正文。"),
    ])
    out = case_index.search(conn, "  ")
    assert out["total"] == 2 and out["sort"] == "newest"
    assert [h["loc"] for h in out["items"]] == ["case_2", "case_1"]
    assert all(h["snippet"] for h in out["items"])


def test_filter_by_field_crime_year(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲故意杀人案", "参考案例", "", ["刑事", "故意杀人罪"],
         "2023.05.01", "", "正文。"),
        ("人民法院案例库", "case_2", "乙盗窃案", "参考案例", "", ["刑事", "盗窃罪"],
         "2021.05.01", "", "正文。"),
        ("人民法院案例库", "case_3", "丙房屋租赁案", "参考案例", "", ["民事", "房屋租赁合同纠纷"],
         "2023.06.01", "", "正文。"),
        ("人民法院案例库", "case_4", "丁无标注案", "参考案例", "", ["其他标签"],
         "2023.07.01", "", "正文。"),
    ])
    assert case_index.search(conn, field="刑事")["total"] == 2
    assert case_index.search(conn, field="民事")["total"] == 1
    assert case_index.search(conn, field="未标注")["total"] == 1
    assert {h["loc"] for h in case_index.search(conn, crime="故意杀人罪")["items"]} == {"case_1"}
    assert case_index.search(conn, year="2023")["total"] == 3
    assert case_index.search(conn, field="刑事", year="2023")["total"] == 1
    assert case_index.search(conn, field="刑事", crime="盗窃罪", year="2023")["total"] == 0


def test_sort_newest_and_oldest(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲案", "参考案例", "", [], "2019.01.01", "", "正文。"),
        ("人民法院案例库", "case_2", "乙案", "参考案例", "", [], "2024-02-03", "", "正文。"),
        ("人民法院案例库", "case_3", "丙案", "参考案例", "", [], "", "", "无日期。"),
    ])
    assert [h["loc"] for h in case_index.search(conn, sort="newest")["items"]] == \
        ["case_2", "case_1", "case_3"]  # 无日期排最后
    assert [h["loc"] for h in case_index.search(conn, sort="oldest")["items"]] == \
        ["case_1", "case_2", "case_3"]
    # 点号与横线混合格式也要按真实时间顺序
    assert [h["loc"] for h in case_index.search(conn, year="2019")["items"]] == ["case_1"]


def test_pagination_offset(conn):
    _seed(conn, [
        (("人民法院案例库"), f"case_{i}", f"第{i}案", "参考案例", "", ["民事"],
         f"2020.01.{i:02d}", "", "正文。") for i in range(1, 6)
    ])
    out = case_index.search(conn, field="民事", sort="oldest", limit=2, offset=2)
    assert out["total"] == 5
    assert [h["loc"] for h in out["items"]] == ["case_3", "case_4"]
    assert out["offset"] == 2


def test_stats(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲案", "参考案例", "", [], "", "", "正文"),
        ("最高法指导性案例", "指导性案例001号", "乙案", "第1批", "", [], "", "", "正文"),
    ])
    out = case_index.stats(conn)
    assert out["total"] == 2
    assert {s["source"]: s["n"] for s in out["sources"]}["人民法院案例库"] == 1
    assert len(out["sources"]) == len(CASE_SOURCES)


def _seed_browse(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲案", "参考案例", "", ["民事"],
         "2019.01.01", "", "旧案正文。"),
        ("人民法院案例库", "case_2", "乙案", "参考案例", "", ["民事"],
         "2024.01.01", "", "新案正文。"),
        ("司法部案例库", "case_3", "丙案", "调解", "", ["民事"],
         "2021.01.01", "", "中案正文。"),
    ])


def test_sort_unviewed_puts_viewed_last(conn):
    """未看过优先：没读过的在前，读过的一组保持组内原序（最新在前）。"""
    _seed_browse(conn)
    case_views.mark_viewed(conn, "人民法院案例库", "case_1")
    out = case_index.search(conn, sort="unviewed")
    assert out["sort"] == "unviewed"
    assert [h["loc"] for h in out["items"]] == ["case_2", "case_3", "case_1"]
    assert [h["viewed"] for h in out["items"]] == [False, False, True]
    # 检索态：未看过优先 + 组内按相关度
    hits = case_index.search(conn, "正文", sort="unviewed")["items"]
    assert [h["loc"] for h in hits] == ["case_2", "case_3", "case_1"]


def test_search_viewed_filter(conn):
    _seed_browse(conn)
    case_views.mark_viewed(conn, "司法部案例库", "case_3")
    assert {h["loc"] for h in case_index.search(conn, viewed_filter="no")["items"]} == \
        {"case_1", "case_2"}
    assert {h["loc"] for h in case_index.search(conn, viewed_filter="yes")["items"]} == \
        {"case_3"}


def test_neighbors_follow_search_order(conn):
    """下一篇必须与同一上下文下 search 的顺序一致；无阅读轨迹时上一篇为空。"""
    _seed_browse(conn)
    ctx = {"field": "民事", "sort": "newest"}
    items = case_index.search(conn, **ctx)["items"]
    assert [h["loc"] for h in items] == ["case_2", "case_3", "case_1"]
    for i, hit in enumerate(items):
        out = case_index.neighbors(conn, hit["source"], hit["loc"], **ctx)
        assert out["index"] == i and out["total"] == 3
        assert out["prev"] is None  # 已经看过的那几篇才进轨迹
        assert (out["next"] or {}).get("loc") == (
            items[i + 1]["loc"] if i + 1 < len(items) else None)


def test_neighbors_prev_is_reading_trail(conn):
    """打完点后本篇会沉到最后：下一篇按「未看过」定位，上一篇走阅读轨迹。"""
    _seed_browse(conn)
    case_views.mark_viewed(conn, "人民法院案例库", "case_2")
    case_views.mark_viewed(conn, "人民法院案例库", "case_3")
    out = case_index.neighbors(conn, "人民法院案例库", "case_3", sort="newest")
    assert out["prev"]["loc"] == "case_2"
    assert out["next"] is None  # 未看过的只剩 case_1，但它排在 case_3 前面
    back = case_index.neighbors(conn, "人民法院案例库", "case_2", sort="newest")
    assert back["prev"] is None
    assert back["next"]["loc"] == "case_3"


def test_neighbors_viewed_filter_no_keeps_next(conn):
    """只看未看过时，打完点本篇不再匹配筛选，但下一篇仍要能给出。"""
    _seed_browse(conn)
    case_views.mark_viewed(conn, "人民法院案例库", "case_2")
    out = case_index.neighbors(conn, "人民法院案例库", "case_2", sort="newest",
                               viewed_filter="no")
    # case_2(2024) 当作未看过定位，下一篇是日期次新的 case_3(2021)
    assert out["next"]["loc"] == "case_3"
