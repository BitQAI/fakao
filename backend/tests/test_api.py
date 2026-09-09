from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import ai, db, importer
from app.main import app


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """API 测试不访问真实 DeepSeek，AI 一律走规则兜底。"""
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(ai, "get_async_client", lambda: None)


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
    assert "morning_report" not in data


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
    assert state["state"] == "weak"


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


def test_listen_queue_api(client, monkeypatch):
    from app import service
    monkeypatch.setattr(service, "ensure_listen_pool", lambda conn, threshold=50: False)
    data = client.get("/api/listen").json()
    assert len(data["items"]) == 1
    assert data["remaining"] == 1
    assert data["generating"] is False


def test_import_rejects_bad_json(client):
    r = client.post("/api/import", files={"file": ("bad.json", b"{broken", "application/json")})
    assert r.status_code == 400


def test_import_promotes_to_final(client):
    import json
    payload = {
        "schema": "fakao-entry/1.0", "generated_at": "x", "count": 1,
        "entries": [{
            "id": "XF-999", "subject": "刑法", "submodule": "分则",
            "point": "Web导入考点", "anchor": "甲实施抢劫行为，使用暴力压制反抗后取得财物，案件事实完整描述",
            "conclusion": "成立罪名。", "priority": "高频考点", "rationale": "高频",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md", "loc": "抢劫罪"}],
            "statutes": [], "note": None, "tts_text": "结论。",
        }],
    }
    r = client.post("/api/import",
                    files={"file": ("web.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")})
    assert r.status_code == 200
    # entry_by_id 仅返回 final：能被查到时即证明已 promote
    assert client.get("/api/entries/XF-999").status_code == 200


def test_marks_crud(client):
    r = client.post("/api/marks", json={"entry_id": "XF-001"})
    assert r.status_code == 200
    mark_id = r.json()["id"]
    # 幂等：重复添加返回同一 id
    assert client.post("/api/marks", json={"entry_id": "XF-001"}).json()["id"] == mark_id
    items = client.get("/api/marks").json()["items"]
    assert len(items) == 1
    assert items[0]["entry"]["point"] == "转化型抢劫"
    assert client.delete(f"/api/marks/{mark_id}").status_code == 200
    assert client.get("/api/marks").json()["items"] == []
    assert client.delete(f"/api/marks/{mark_id}").status_code == 404


def test_marks_missing_entry_404(client):
    assert client.post("/api/marks", json={"entry_id": "NOPE-001"}).status_code == 404


def test_marks_clear(client):
    client.post("/api/marks", json={"entry_id": "XF-001"})
    assert client.delete("/api/marks").status_code == 200
    assert client.get("/api/marks").json()["items"] == []


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


def test_statute_kuan_suffix(client, tmp_path, monkeypatch):
    """带「款」引用的法条（刑法第20条第3款）应解析到整条正文。"""
    from app import config, statutes
    monkeypatch.setattr(config, "STATUTE_DIR", tmp_path)
    (tmp_path / "中华人民共和国刑法.md").write_text(
        "第二十条　为了使国家、公共利益、本人或者他人的人身、财产和其他权利"
        "免受正在进行的不法侵害，而采取的制止不法侵害的行为，对不法侵害人造成损害的，"
        "属于正当防卫，不负刑事责任。",
        encoding="utf-8",
    )
    statutes._STATUTE_CACHE.clear()
    statutes._LAW_FILE_CACHE.clear()
    r = client.get("/api/statute", params={"law": "刑法", "no": "20条第3款"})
    assert r.status_code == 200
    assert "正当防卫" in r.json()["text"]


def test_statute_missing_404(client, tmp_path, monkeypatch):
    from app import config, statutes
    monkeypatch.setattr(config, "STATUTE_DIR", tmp_path)
    statutes._STATUTE_CACHE.clear()
    statutes._LAW_FILE_CACHE.clear()
    r = client.get("/api/statute", params={"law": "刑法", "no": "999"})
    assert r.status_code == 404


def test_listen_limit_param(client, monkeypatch):
    from app import service
    monkeypatch.setattr(service, "ensure_listen_pool", lambda conn, threshold=50: False)
    data = client.get("/api/listen", params={"limit": 1}).json()
    assert len(data["items"]) == 1
    # 非法值应钳制而非 500
    assert client.get("/api/listen", params={"limit": 0}).status_code == 200


def test_update_entry_text_ok_and_validation(client):
    good = {
        "point": "转化型抢劫修正",
        "anchor": "甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤呀",
        "conclusion": "成立抢劫罪。",
        "priority": "易错陷阱",
        "note": "注意当场性。",
    }
    r = client.put("/api/entries/XF-001", json=good)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["point"] == "转化型抢劫修正"
    assert data["priority"] == "易错陷阱"
    # tts/音频字段不受影响，条目仍为 final 可查
    assert data["tts_text"].startswith("【刑法·转化型抢劫】")
    assert client.get("/api/entries/XF-001").json()["note"] == "注意当场性。"
    # 锚点过短 → 400
    bad = dict(good, anchor="太短了")
    assert client.put("/api/entries/XF-001", json=bad).status_code == 400
    # 结论不以句号结尾 → 400
    bad2 = dict(good, conclusion="成立抢劫罪")
    assert client.put("/api/entries/XF-001", json=bad2).status_code == 400
    # 非法优先级 → 400
    bad3 = dict(good, priority="必考")
    assert client.put("/api/entries/XF-001", json=bad3).status_code == 400
    # 不存在 → 404
    assert client.put("/api/entries/NOPE-001", json=good).status_code == 404


def test_assistant_history_by_entry(client):
    r = client.post("/api/assistant/ask", json={"question": "转化型抢劫是什么", "entry_id": "XF-001"})
    assert r.status_code == 200
    items = client.get("/api/assistant/history", params={"entry_id": "XF-001"}).json()["items"]
    assert len(items) >= 1
    assert "XF-001" in items[0]["related_entry_ids"]
    assert "转化型抢劫是什么" in items[0]["question"]
    # 前缀 id 不得误配：XF-001 的记录不应出现在 XF-0010 下
    assert client.get("/api/assistant/history", params={"entry_id": "XF-0010"}).json()["items"] == []
    assert client.get("/api/assistant/history", params={"entry_id": " "}).status_code == 400
