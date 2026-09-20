"""法条检索 API 测试。"""
import pytest
from fastapi.testclient import TestClient

from app import db
from app import statute_index as si
from app.main import app


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "statutes.db"
    conn = db.connect(db_path)
    conn.execute(
        "INSERT INTO entries (id, subject, submodule, point, anchor, conclusion, "
        "priority, rationale, sources, cases, statutes, note, tts_text, status) "
        "VALUES ('XF-001','刑法','总则-犯罪构成','正当防卫','情境','结论',"
        "'高频考点','理由','[]','[]','[\"刑法第20条\"]','','文本','final')")
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


def test_list_statutes(client):
    items = client.get("/api/statutes").json()["items"]
    keys = {i["key"] for i in items}
    assert "中华人民共和国公司法" in keys
    assert "中华人民共和国民法典" in keys
    assert len(items) >= 55


def test_get_law_with_pagination(client):
    data = client.get("/api/statutes/中华人民共和国公司法",
                      params={"offset": 0, "limit": 5}).json()
    assert data["total"] == 266
    assert len(data["items"]) == 5
    assert data["items"][0]["label"] == "第一条"
    assert data["chapters"]


def test_get_unknown_law_404(client):
    assert client.get("/api/statutes/不存在法").status_code == 404


def test_get_law_accepts_short_name(client):
    """条目里用的是简称（如「刑法」），接口应能解析到对应文件。"""
    data = client.get("/api/statutes/刑法").json()
    assert data["key"] == "中华人民共和国刑法"
    assert data["total"] == 505


def test_search_statute(client):
    items = client.get("/api/statute/search", params={"q": "表见代理"}).json()["items"]
    assert items
    assert all("表见代理" in i["snippet"] for i in items)


def test_search_empty_query(client):
    assert client.get("/api/statute/search", params={"q": ""}).json()["items"] == []


def test_statute_entries_reverse_index(client):
    items = client.get("/api/statute/entries",
                       params={"law": "中华人民共和国刑法", "no": 20}).json()["items"]
    assert [i["id"] for i in items] == ["XF-001"]


def test_existing_single_statute_endpoint_unchanged(client):
    """原有 /api/statute 单条接口不受新路由影响。"""
    data = client.get("/api/statute", params={"law": "刑法", "no": "20"}).json()
    assert "正当防卫" in data["text"]


def test_index_cache_reusable(client):
    assert si.load_library()["中华人民共和国刑法"].article(232) is not None
