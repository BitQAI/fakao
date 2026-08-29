from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import ai, db, importer
from app.main import app


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)


def seed(conn):
    entries = [{
        "id": "XF-001", "subject": "刑法", "submodule": "分则-财产犯罪",
        "point": "转化型抢劫",
        "anchor": "甲盗窃后为抗拒抓捕当场使用暴力将失主打伤",
        "conclusion": "成立抢劫罪。", "priority": "高频考点",
        "rationale": "高频",
        "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                     "loc": "犯盗窃罪，为抗拒抓捕而当场使用暴力"}],
        "statutes": ["刑法269条"],
        "note": None, "tts_override": None,
        "tts_text": "【刑法·转化型抢劫】……成立抢劫罪。",
    }, {
        "id": "MF-001", "subject": "民法", "submodule": "总则-法律行为",
        "point": "民事行为能力",
        "anchor": "六岁儿童独自在商场购买游戏机家长拒绝追认",
        "conclusion": "行为无效。", "priority": "易错陷阱",
        "rationale": "易错",
        "sources": [{"type": "易错", "ref": "民法-易错点.md",
                     "loc": "无民事行为能力人实施的民事法律行为无效"}],
        "statutes": ["民法典144条"],
        "note": None, "tts_override": None,
        "tts_text": "【民法·民事行为能力】……行为无效。",
    }]
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": 2,
                                   "entries": entries})


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "api.db"
    conn = db.connect(db_path)
    seed(conn)
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


def _review(client, entry_id, mode, result, duration=10):
    r = client.post("/api/reviews", json={
        "entry_id": entry_id, "mode": mode, "result": result,
        "duration_sec": duration,
    })
    assert r.status_code == 200


def test_entry_deep_link(client):
    data = client.get("/api/entries/XF-001").json()
    assert data["id"] == "XF-001"
    assert data["subject"] == "刑法"
    assert client.get("/api/entries/NOPE").status_code == 404


def test_review_history(client):
    _review(client, "XF-001", "read", "bad")
    _review(client, "XF-001", "listen", "exposed")
    _review(client, "MF-001", "listen", "exposed")
    data = client.get("/api/reviews/history").json()["items"]
    assert len(data) == 3
    assert data[0]["mode"] == "listen"
    assert data[0]["entry"]["point"] == "民事行为能力"
    # 时间倒序
    ts = [it["ts"] for it in data]
    assert ts == sorted(ts, reverse=True)
    # mode 过滤
    reads = client.get("/api/reviews/history?mode=read").json()["items"]
    assert len(reads) == 1 and reads[0]["mode"] == "read"
    listens = client.get("/api/reviews/history?mode=listen").json()["items"]
    assert len(listens) == 2
    assert client.get("/api/reviews/history?mode=quiz").status_code == 400


def test_leaderboard_aggregates(client):
    _review(client, "XF-001", "read", "good")
    _review(client, "XF-001", "read", "fuzzy")
    _review(client, "XF-001", "listen", "exposed")
    _review(client, "XF-001", "listen", "exposed")
    _review(client, "MF-001", "read", "bad")
    items = client.get("/api/leaderboard").json()["items"]
    assert len(items) == 2
    top = items[0]
    assert top["entry_id"] == "XF-001"
    assert top["read_count"] == 2
    assert top["listen_count"] == 2
    assert top["total_count"] == 4
    assert top["read_repeat"] == 1
    assert top["listen_repeat"] == 1
    # 只看
    reads = client.get("/api/leaderboard?sort=read").json()["items"]
    assert reads[0]["entry_id"] == "XF-001"
    # 只听
    listens = client.get("/api/leaderboard?sort=listen").json()["items"]
    assert listens[0]["entry_id"] == "XF-001"
    assert listens[1]["listen_count"] == 0
    assert client.get("/api/leaderboard?sort=bad").status_code == 400


def test_listen_marks_heard(client):
    _review(client, "MF-001", "listen", "exposed", duration=16)
    data = client.get("/api/listen").json()
    assert data["heard_total"] == 1
    by_id = {it["id"]: it for it in data["items"]}
    assert by_id["MF-001"]["listen_count"] == 1
    assert by_id["MF-001"]["last_ts"]
    assert by_id["XF-001"]["listen_count"] == 0
    assert by_id["XF-001"]["last_ts"] is None
    # 未听优先：XF-001 应在 MF-001 前面
    assert data["items"][0]["id"] == "XF-001"
