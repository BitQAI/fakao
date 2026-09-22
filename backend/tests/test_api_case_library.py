"""案例库检索 API 测试。"""
import json

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "caselib.db"
    conn = db.connect(db_path)
    conn.executemany(
        "INSERT INTO cases (source, loc, title, category, case_no, keywords, date, "
        "url, text) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("人民法院案例库", "case_1", "房屋租赁合同纠纷案", "参考案例",
             "（2018）苏06民终4610号", json.dumps(["民事", "房屋租赁"], ensure_ascii=False),
             "2019.02.26", "https://example.com/1",
             "1.承租人擅自变动房屋建筑主体，应予支持。\n承租人拒不恢复原状的，应赔偿。"),
            ("最高检指导性案例", "检例第39号", "朱炜明操纵证券市场案", "第9批", "",
             json.dumps(["刑事", "操纵证券市场罪"], ensure_ascii=False), "2018-12-25", "",
             "【关键词】\n操纵证券市场\n【要旨】\n情节严重的，追究刑事责任。"),
        ])
    conn.commit()
    conn.close()

    def override_get_db():
        c = db.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[db.get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_search_hits(client):
    body = client.get("/api/case/search", params={"q": "房屋 租赁"}).json()
    assert body["total"] == 1
    assert body["items"][0]["loc"] == "case_1"
    assert "承租" in body["items"][0]["snippet"]
    assert body["items"][0]["keywords"] == ["民事", "房屋租赁"]
    assert "text" not in body["items"][0]


def test_search_source_filter(client):
    assert client.get("/api/case/search", params={"q": "租赁"}).json()["total"] == 1
    assert client.get("/api/case/search",
                      params={"q": "租赁", "source": "司法部案例库"}).json()["total"] == 0


def test_browse_mode_returns_list(client):
    """空 q：浏览模式按日期倒序返回全部，而不是空结果。"""
    body = client.get("/api/case/search", params={"q": ""}).json()
    assert body["total"] == 2 and body["sort"] == "newest"
    assert [i["loc"] for i in body["items"]] == ["case_1", "检例第39号"]
    assert body["items"][0]["snippet"]


def test_filters_and_sort(client):
    assert client.get("/api/case/search", params={"field": "民事"}).json()["total"] == 1
    assert client.get("/api/case/search", params={"field": "刑事"}).json()["total"] == 1
    assert client.get("/api/case/search", params={"year": "2019"}).json()["total"] == 1
    oldest = client.get("/api/case/search", params={"sort": "oldest"}).json()
    assert [i["loc"] for i in oldest["items"]] == ["检例第39号", "case_1"]
    assert oldest["sort"] == "oldest"


def test_search_pagination(client):
    body = client.get("/api/case/search",
                      params={"limit": 1, "offset": 1, "sort": "newest"}).json()
    assert body["total"] == 2 and body["limit"] == 1 and body["offset"] == 1
    assert [i["loc"] for i in body["items"]] == ["检例第39号"]


def test_search_invalid_params_400(client):
    assert client.get("/api/case/search", params={"sort": "乱序"}).status_code == 400
    assert client.get("/api/case/search", params={"field": "宇宙法"}).status_code == 400
    assert client.get("/api/case/search", params={"year": "23"}).status_code == 400
    assert client.get("/api/case/search", params={"viewed": "也许"}).status_code == 400


def _view(client, source, loc):
    return client.post("/api/case/view", json={"source": source, "loc": loc})


def test_view_marks_case_viewed(client):
    """打点幂等：首次 first_time，重复累计 views；列表回显 viewed。"""
    assert client.get("/api/case/search", params={"q": "房屋"}
                      ).json()["items"][0]["viewed"] is False
    first = _view(client, "人民法院案例库", "case_1").json()
    assert first["views"] == 1 and first["first_time"] is True
    again = _view(client, "人民法院案例库", "case_1").json()
    assert again["views"] == 2 and again["first_time"] is False
    hit = client.get("/api/case/search", params={"q": "房屋"}).json()["items"][0]
    assert hit["viewed"] is True


def test_view_unknown_case_404(client):
    assert _view(client, "人民法院案例库", "case_404").status_code == 404
    assert _view(client, "不存在的库", "case_1").status_code == 404


def test_unviewed_sort_and_viewed_filters(client):
    """未看过优先：看过的沉底；viewed=no/yes 只看一侧。"""
    _view(client, "人民法院案例库", "case_1")
    body = client.get("/api/case/search", params={"sort": "unviewed"}).json()
    assert body["sort"] == "unviewed"
    assert [i["loc"] for i in body["items"]] == ["检例第39号", "case_1"]
    fresh = client.get("/api/case/search", params={"viewed": "no"}).json()
    assert [i["loc"] for i in fresh["items"]] == ["检例第39号"]
    seen = client.get("/api/case/search", params={"viewed": "yes"}).json()
    assert [i["loc"] for i in seen["items"]] == ["case_1"]
    assert seen["filters"]["viewed"] == "yes"


def test_neighbors_walks_browse_order(client):
    head = client.get("/api/case/neighbors",
                      params={"lib": "人民法院案例库", "loc": "case_1",
                              "sort": "newest"}).json()
    assert head["index"] == 0 and head["total"] == 2 and head["prev"] is None
    assert head["next"]["loc"] == "检例第39号"
    tail = client.get("/api/case/neighbors",
                      params={"lib": "最高检指导性案例", "loc": "检例第39号",
                              "sort": "newest"}).json()
    assert tail["index"] == 1 and tail["next"] is None and tail["prev"] is None


def test_neighbors_prev_follows_reading_trail(client):
    """打点会把人挪到「已看过」组末尾，所以上一篇按阅读轨迹取。"""
    _view(client, "人民法院案例库", "case_1")
    _view(client, "最高检指导性案例", "检例第39号")
    out = client.get("/api/case/neighbors",
                     params={"lib": "最高检指导性案例", "loc": "检例第39号"}).json()
    assert out["prev"]["loc"] == "case_1"
    back = client.get("/api/case/neighbors",
                      params={"lib": "人民法院案例库", "loc": "case_1"}).json()
    assert back["prev"] is None  # 再往前没有读过别的
    assert back["next"]["loc"] == "检例第39号"  # 但能顺着继续读


def test_neighbors_respects_query_context(client):
    """检索上下文里当前篇不命中 → 无下一篇（防御分支，前端隐藏按钮）。"""
    body = client.get("/api/case/neighbors",
                      params={"lib": "人民法院案例库", "loc": "case_1",
                              "q": "操纵证券市场"}).json()
    assert body["index"] == -1 and body["prev"] is None and body["next"] is None


def test_neighbors_out_of_context_still_goes_back(client):
    """从历史记录带着老筛选跳进来时，下一篇没有，但还能退回刚看过的那篇。"""
    _view(client, "最高检指导性案例", "检例第39号")
    body = client.get("/api/case/neighbors",
                      params={"lib": "人民法院案例库", "loc": "case_1",
                              "q": "操纵证券市场"}).json()
    assert body["index"] == -1 and body["next"] is None
    assert body["prev"]["loc"] == "检例第39号"


def test_neighbors_invalid_params(client):
    base = {"lib": "人民法院案例库", "loc": "case_1"}
    assert client.get("/api/case/neighbors",
                      params={**base, "sort": "乱序"}).status_code == 400
    assert client.get("/api/case/neighbors",
                      params={**base, "viewed": "也许"}).status_code == 400
    assert client.get("/api/case/neighbors",
                      params={"lib": "不存在的库", "loc": "case_1"}).status_code == 404


def test_history_and_clear(client):
    _view(client, "人民法院案例库", "case_1")
    body = client.get("/api/case/history").json()
    assert body["total"] == 1
    assert body["items"][0]["loc"] == "case_1"
    assert body["items"][0]["title"] == "房屋租赁合同纠纷案"
    assert client.delete("/api/case/history").json()["cleared"] == 1
    assert client.get("/api/case/history").json()["items"] == []
    # 清空同时重置「看过」标记，列表回到未看过
    assert client.get("/api/case/search", params={"q": "房屋"}
                      ).json()["items"][0]["viewed"] is False


def test_facets(client):
    body = client.get("/api/case/facets").json()
    assert body["total"] == 2
    assert {f["value"]: f["n"] for f in body["fields"]}["民事"] == 1
    assert {c["value"]: c["n"] for c in body["crimes"]}["操纵证券市场罪"] == 1
    assert {y["value"]: y["n"] for y in body["years"]} == {"2019": 1, "2018": 1}


def test_search_unknown_source_404(client):
    res = client.get("/api/case/search", params={"q": "租赁", "source": "不存在的库"})
    assert res.status_code == 404


def test_detail_returns_sections(client):
    body = client.get("/api/case/detail",
                      params={"source": "人民法院案例库", "loc": "case_1"}).json()
    assert body["title"] == "房屋租赁合同纠纷案"
    assert [s["label"] for s in body["sections"]] == ["裁判要旨", ""]
    assert body["keywords"] == ["民事", "房屋租赁"]


def test_detail_bracket_sections(client):
    body = client.get("/api/case/detail",
                      params={"source": "最高检指导性案例", "loc": "检例第39号"}).json()
    assert [s["label"] for s in body["sections"]] == ["关键词", "要旨"]


def test_detail_missing_case_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CASES_DOCS_DIR", tmp_path / "none")
    res = client.get("/api/case/detail",
                     params={"source": "人民法院案例库", "loc": "case_404"})
    assert res.status_code == 404


def test_stats(client):
    body = client.get("/api/case/stats").json()
    assert body["total"] == 2
    assert {s["source"]: s["n"] for s in body["sources"]}["人民法院案例库"] == 1


def test_subjective_case_route_not_shadowed(client):
    """/api/cases/{qid} 是主观题接口，不能被案例库路由抢走（曾经 422 的坑）。"""
    res = client.get("/api/cases/1")
    assert res.status_code == 404
    assert "案例题不存在" in res.text
