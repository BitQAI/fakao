"""案例库分面聚合测试。"""
import json

import pytest

from app import case_facets, db


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


def test_case_year():
    assert case_facets.case_year("2023.05.01") == "2023"
    assert case_facets.case_year("2018-12-25") == "2018"
    assert case_facets.case_year("") == ""
    assert case_facets.case_year("不详") == ""


def test_crimes_of_excludes_non_crimes():
    kws = ["刑事", "故意杀人罪", "无罪", "共同犯罪", "量刑"]
    assert case_facets.crimes_of(kws) == ["故意杀人罪", "共同犯罪"]


def test_field_of():
    assert case_facets.field_of(["刑事", "盗窃罪"]) == "刑事"
    assert case_facets.field_of(["其他标签"]) == case_facets.UNLABELED
    assert case_facets.field_of([]) == case_facets.UNLABELED


def test_facets_counts_and_partition(conn):
    _seed(conn, [
        ("人民法院案例库", "case_1", "甲案", "参考案例", "", ["刑事", "故意杀人罪", "无罪"],
         "2023.01.01", "", "正文"),
        ("人民法院案例库", "case_2", "乙案", "参考案例", "", ["刑事", "盗窃罪"],
         "2023.02.01", "", "正文"),
        ("司法部案例库", "case_3", "丙案", "调解", "", ["民事", "房屋租赁合同纠纷"],
         "2021-03-04", "", "正文"),
        ("最高检指导性案例", "检例第1号", "丁案", "第1批", "", ["其他词"],
         "", "", "正文"),
    ])
    out = case_facets.facets(conn)
    fields = {f["value"]: f["n"] for f in out["fields"]}
    assert fields["刑事"] == 2 and fields["民事"] == 1
    assert fields[case_facets.UNLABELED] == 1
    assert sum(fields.values()) == out["total"] == 4  # 分面是分区，可加总
    crimes = {c["value"]: c["n"] for c in out["crimes"]}
    assert crimes["故意杀人罪"] == 1 and crimes["盗窃罪"] == 1
    assert "无罪" not in crimes  # 非罪名不入维度
    years = {y["value"]: y["n"] for y in out["years"]}
    assert years == {"2023": 2, "2021": 1}  # 无日期不进年份分面
    assert [y["value"] for y in out["years"]] == ["2023", "2021"]  # 年份倒序
    sources = {s["value"]: s["n"] for s in out["sources"]}
    assert sources["人民法院案例库"] == 2 and sources["最高法指导性案例"] == 0
