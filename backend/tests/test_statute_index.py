"""法条库索引层测试：目录解析、条号归一、检索、反向索引。"""
from pathlib import Path

from app import db, statute_index

SAMPLE = """# 中华人民共和国示例法

- 公布日期：2026-01-01  施行日期：2026-06-01  效力状态：3  制定机关：全国人民代表大会常务委员会
- 来源：国家法律法规数据库 flk.npc.gov.cn (bbbs=test)

中华人民共和国示例法

目　　录

第一章　总　　则

第二章　合　　同

　　第一节　订立

第一章　总　　则

第一条　为了示例，制定本法。

第二条　本法所称合同，是指民事主体之间设立、变更、终止民事法律关系的协议。
第二款内容。

第二章　合　　同

　　第一节　订立

第三条　当事人订立合同，可以采用书面形式。

第四条　本法和《中华人民共和国示例法》第二百八十七条之二同样适用。
"""


def _library(tmp_path: Path) -> Path:
    (tmp_path / "中华人民共和国示例法.md").write_text(SAMPLE, encoding="utf-8")
    statute_index.clear_cache()
    return tmp_path


def test_parse_meta_and_articles(tmp_path):
    law = statute_index.load_library(_library(tmp_path))["中华人民共和国示例法"]
    assert law.meta["公布日期"] == "2026-01-01"
    assert law.meta["效力状态"] == "3"
    assert len(law.articles) == 4


def test_toc_is_skipped_and_chapters_attached(tmp_path):
    law = statute_index.load_library(_library(tmp_path))["中华人民共和国示例法"]
    assert law.article(1).chapter == ("第一章　总　　则",)
    assert law.article(3).chapter == ("第二章　合　　同", "第一节　订立")


def test_multi_paragraph_article_kept(tmp_path):
    law = statute_index.load_library(_library(tmp_path))["中华人民共和国示例法"]
    assert "第二款内容。" in law.article(2).text
    assert law.article(2).text.startswith("本法所称合同")


AMENDMENT = """# 中华人民共和国示例法修正案（一）

- 公布日期：2026-01-01  施行日期：2026-06-01  效力状态：3  制定机关：全国人民代表大会常务委员会
- 来源：国家法律法规数据库 flk.npc.gov.cn (bbbs=test)

中华人民共和国示例法修正案（一）

（2026年1月1日第十四届全国人民代表大会常务委员会第一次会议通过）

一、在示例法第一百六十五条中增加一款作为第二款，将该条修改为：“国有公司、企业的董事、
监事、高级管理人员，利用职务便利获取非法利益，数额巨大的，处三年以下有期徒刑。”

二、将示例法第三百九十条修改为：“对犯行贿罪的，处三年以下有期徒刑或者拘役，并处罚金。”

三、本修正案自2026年6月1日起施行。
"""


def test_ordinal_articles_for_amendment_files(tmp_path):
    """刑法修正案/单行解释用「一、二、三、」而非「第X条」，也要能被解析成条文。"""
    (tmp_path / "中华人民共和国示例法修正案（一）.md").write_text(
        AMENDMENT, encoding="utf-8")
    statute_index.clear_cache()
    law = statute_index.load_library(tmp_path)["中华人民共和国示例法修正案（一）"]
    assert [a.label for a in law.articles] == ["第一条", "第二条", "第三条"]
    assert "一百六十五条" in law.article(1).text
    assert "三年以下有期徒刑" in law.article(2).text
    # 未按「第X条」解析的文件才走序号兜底，正常文件不受影响
    assert law.article(1).text.count("二、") == 0


def test_label_and_int2cn():
    assert statute_index.int2cn(10) == "十"
    assert statute_index.int2cn(21) == "二十一"
    assert statute_index.int2cn(101) == "一百零一"
    assert statute_index.int2cn(1165) == "一千一百六十五"
    art = statute_index.Article(20, 3, "x", ())
    assert art.label == "第二十条之三"


def test_search_returns_snippet_with_context(tmp_path):
    hits = statute_index.search("书面形式", directory=_library(tmp_path))
    assert len(hits) == 1
    assert hits[0]["no"] == 3
    assert "书面形式" in hits[0]["snippet"]
    assert statute_index.search("", directory=tmp_path) == []


def test_law_payload_paginates(tmp_path):
    directory = _library(tmp_path)
    payload = statute_index.law_payload("中华人民共和国示例法", offset=1, limit=2,
                                        directory=directory)
    assert payload["total"] == 4
    assert [i["no"] for i in payload["items"]] == [2, 3]
    assert statute_index.law_payload("不存在", directory=directory) is None


def test_short_names_includes_alias():
    names = statute_index.short_names(
        "最高人民法院关于适用《中华人民共和国公司法》若干问题的规定（三）")
    assert "公司法解释三" in names
    assert "公司法" not in names


def _insert_entry(conn, entry_id: str, statutes_json: str) -> None:
    conn.execute(
        "INSERT INTO entries (id, subject, submodule, point, anchor, conclusion, "
        "priority, rationale, sources, cases, statutes, note, tts_text, status) "
        "VALUES (?, '公司法','组织机构','考点','情境','结论','高频考点',"
        "'理由','[]','[]',?,'','文本','final')", (entry_id, statutes_json))


def test_entries_for_reverse_index(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _insert_entry(conn, "X-001", '["公司法第10条"]')
    _insert_entry(conn, "X-002", '["中华人民共和国公司法第10条"]')
    conn.commit()
    hits = statute_index.entries_for(conn, "中华人民共和国公司法", 10)
    assert {h["id"] for h in hits} == {"X-001", "X-002"}
    assert statute_index.entries_for(conn, "中华人民共和国公司法", 999) == []
    conn.close()
