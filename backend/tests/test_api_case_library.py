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
             json.dumps(["操纵证券市场"], ensure_ascii=False), "2018-12-25", "",
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


def test_search_source_filter_and_empty_query(client):
    assert client.get("/api/case/search", params={"q": "租赁"}).json()["total"] == 1
    assert client.get("/api/case/search",
                      params={"q": "租赁", "source": "司法部案例库"}).json()["total"] == 0
    assert client.get("/api/case/search", params={"q": ""}).json()["items"] == []


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
