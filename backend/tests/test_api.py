from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db, importer
from app.main import app


def seed(conn):
    entries = [{
        "id": "XF-001", "subject": "刑法", "submodule": "分则-财产犯罪",
        "point": "转化型抢劫", "anchor": "甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤",
        "conclusion": "成立抢劫罪。", "priority": "高频考点",
        "rationale": "高频", "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                                          "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
        "statutes": ["刑法269条"], "note": None, "tts_override": None,
        "tts_text": "【刑法·转化型抢劫】甲盗窃后……成立抢劫罪。"}]
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": 1, "entries": entries})


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "api.db"
    conn = db.connect(db_path)
    seed(conn)
    conn.execute(
        "INSERT INTO cases (source, loc, title, category, case_no, keywords, date, url, text) "
        "VALUES ('人民法院案例库','case_00001','甲诉乙案','参考案例','（2026）苏01民终1号',"
        "'[\"民事\"]','2026-01-01','','案情正文')"
    )
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


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_today(client):
    data = client.get("/api/today").json()
    assert data["plan"]["quota"] == 1
    assert data["stats"]["quota"] == 1
    assert data["morning_report"]["content"]


def test_settings_roundtrip(client):
    r = client.put("/api/settings", json={"exam_date": "2026-09-13", "capacity_max": 80})
    assert r.status_code == 200
    assert r.json()["days_left"] == (date(2026, 9, 13) - date.today()).days
    assert r.json()["capacity_max"] == 80


def test_settings_bad_date(client):
    r = client.put("/api/settings", json={"exam_date": "not-a-date"})
    assert r.status_code == 400


def test_review_then_coverage(client):
    assert client.post("/api/reviews", json={
        "entry_id": "XF-001", "mode": "read", "result": "bad", "duration_sec": 3
    }).json() == {"ok": True}
    tree = client.get("/api/coverage").json()
    state = tree["刑法"]["submodules"]["分则-财产犯罪"]["points"]["转化型抢劫"]
    assert state == "weak"


def test_review_bad_result_rejected(client):
    assert client.post("/api/reviews", json={
        "entry_id": "XF-001", "mode": "read", "result": "nonsense"
    }).status_code == 400


def test_quiz_flow(client):
    questions = client.get("/api/quiz/today").json()["questions"]
    assert len(questions) == 1
    q = questions[0]
    r = client.post("/api/quiz/answer", json={"quiz_id": q["id"], "user_answer": "X"})
    assert r.status_code == 200
    assert r.json()["correct"] is False


def test_import_rejects_bad_json(client):
    r = client.post("/api/import", files={"file": ("bad.json", b"{broken", "application/json")})
    assert r.status_code == 400


def test_assistant_streams_fallback(client):
    r = client.post("/api/assistant/ask", json={"question": "转化型抢劫是什么"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "未配置" in r.text


def test_audio_missing_entry_404(client):
    assert client.get("/api/audio/NOPE-001").status_code == 404


def test_audio_returns_wav(client, tmp_path, monkeypatch):
    from app import tts
    wav = tmp_path / "XF-001.wav"
    wav.write_bytes(b"RIFFfakewav")
    monkeypatch.setattr(tts, "ensure_mp3", lambda *a, **k: wav)
    r = client.get("/api/audio/XF-001")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == b"RIFFfakewav"


def test_source_file_found(client, tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path)
    (tmp_path / "刑法-高频考点.md").write_text(
        "# 高频\n\n犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力。\n正文",
        encoding="utf-8",
    )
    r = client.get("/api/source", params={
        "ref": "刑法-高频考点.md",
        "loc": "为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力",
    })
    assert r.status_code == 200
    data = r.json()
    # /api/source 按 spec 返回命中段落（loc 所在行），非全文
    assert data["kind"] == "file" and "当场使用暴力" in data["text"]
    assert data["offset"] is not None


def test_source_case_lookup(client):
    # 先装载案例库（用临时 index 单条）
    r = client.get("/api/source", params={"ref": "人民法院案例库", "loc": "case_00001"})
    assert r.status_code == 200
    data = r.json()
    assert data["kind"] == "case" and data["title"] == "甲诉乙案"


def test_source_missing_404(client):
    r = client.get("/api/source", params={"ref": "不存在.md"})
    assert r.status_code == 404


def test_statute_ok(client, tmp_path, monkeypatch):
    from app import config, statutes
    monkeypatch.setattr(config, "STATUTE_DIR", tmp_path)
    (tmp_path / "中华人民共和国刑法.md").write_text(
        "第二百六十九条　犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力。",
        encoding="utf-8",
    )
    statutes._STATUTE_CACHE.clear()
    statutes._LAW_FILE_CACHE.clear()
    r = client.get("/api/statute", params={"law": "刑法", "no": "269"})
    assert r.status_code == 200
    assert "窝藏赃物" in r.json()["text"]


def test_statute_missing_404(client, tmp_path, monkeypatch):
    from app import config, statutes
    monkeypatch.setattr(config, "STATUTE_DIR", tmp_path)
    statutes._STATUTE_CACHE.clear()
    statutes._LAW_FILE_CACHE.clear()
    r = client.get("/api/statute", params={"law": "刑法", "no": "999"})
    assert r.status_code == 404
