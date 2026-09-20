"""每日案例 API 测试。"""
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

POINTS = [
    {"no": 1, "kind": "结论", "text": "采分点一", "statutes": ["民法典第172条"]},
    {"no": 2, "kind": "涵摄", "text": "采分点二", "statutes": []},
]

MATERIAL = ("宪法是国家的根本法，是治国安邦的总章程，具有最高的法律效力，"
            "坚持依宪治国、依宪执政是全面依法治国的首要任务。")


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "cases_quiz.db"
    conn = db.connect(db_path)
    conn.execute(
        "INSERT INTO cases (source, loc, title, category, case_no, keywords, date,"
        " url, text) VALUES ('人民法院案例库','case_00001','甲诉乙案','参考案例',"
        "'（2026）苏01民终1号','[\"民事\"]','2026-01-01','','案情')")
    conn.execute(
        "INSERT INTO case_questions (case_source, case_loc, subject, stem, questions,"
        " points, reference, status, created_at) VALUES ('人民法院案例库','case_00001',"
        "'民法','甲持空白合同以乙名义签约。',?,?,'参考：乙承担责任。','published',"
        "'2026-09-20')",
        (json.dumps(["丙能否要求乙承担责任？"], ensure_ascii=False),
         json.dumps(POINTS, ensure_ascii=False)))
    conn.execute(
        "INSERT INTO case_questions (case_source, case_loc, subject, qtype, stem,"
        " questions, points, materials, reference, status, created_at) VALUES"
        " ('法治思想-核心论述','essay-001','理论法','essay','请阅读材料回答。',?,?,?,"
        "'提纲。','published','2026-09-20')",
        (json.dumps(["谈谈你的认识。"], ensure_ascii=False),
         json.dumps([{"no": 1, "kind": "总论点", "text": "依宪治国首要任务",
                      "statutes": []}], ensure_ascii=False),
         json.dumps([{"label": "材料一", "text": MATERIAL}], ensure_ascii=False)))
    conn.execute(
        "INSERT INTO case_questions (case_source, case_loc, subject, qtype, stem,"
        " questions, points, reference, status, created_at) VALUES"
        " ('人民法院案例库','case_08888','民法','composite','长案情。',?,?,'提纲。',"
        "'published','2026-09-20')",
        (json.dumps(["甲能否请求付款？", "由哪个法院管辖？"], ensure_ascii=False),
         json.dumps([{"no": 1, "qno": 1, "kind": "结论", "text": "可以",
                      "statutes": []}], ensure_ascii=False)))
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


def test_daily_does_not_leak_answer(client):
    data = client.get("/api/cases/daily").json()
    q = data["question"]
    assert q["stem"] and q["questions"]
    assert "points" not in q and "reference" not in q
    assert q["case"]["title"] == "甲诉乙案"
    assert data["stats"]["published"] == 1


def test_answer_then_grade(client):
    qid = client.get("/api/cases/daily").json()["question"]["id"]
    ans = client.post(f"/api/cases/{qid}/answer",
                      json={"answer_text": "我写", "duration_sec": 90}).json()
    assert len(ans["points"]) == 2
    got = client.get(f"/api/cases/{qid}").json()
    assert got["points"] and got["reference"]
    graded = client.post(f"/api/cases/{qid}/grade",
                         json={"hit_points": [1]}).json()
    assert graded["score"] == 50
    assert [m["no"] for m in graded["missed"]] == [2]


def test_answer_rejects_bad_mode(client):
    qid = client.get("/api/cases/daily").json()["question"]["id"]
    r = client.post(f"/api/cases/{qid}/answer", json={"mode": "typing"})
    assert r.status_code == 422


def test_unknown_question_404(client):
    assert client.get("/api/cases/999").status_code == 404
    assert client.post("/api/cases/999/answer", json={}).status_code == 404
    assert client.post("/api/cases/999/grade", json={"hit_points": []}).status_code == 404


def test_history_and_stats(client):
    qid = client.get("/api/cases/daily").json()["question"]["id"]
    client.post(f"/api/cases/{qid}/answer", json={"answer_text": "x"})
    client.post(f"/api/cases/{qid}/grade", json={"hit_points": [1, 2]})
    data = client.get("/api/cases/history").json()
    assert data["items"][0]["score"] == 100
    assert data["stats"]["attempts"] == 1
    assert data["stats"]["questions_done"] == 1


def test_misses_endpoint(client):
    qid = client.get("/api/cases/daily").json()["question"]["id"]
    client.post(f"/api/cases/{qid}/answer", json={"answer_text": "x"})
    client.post(f"/api/cases/{qid}/grade", json={"hit_points": [1]})
    items = client.get("/api/cases/misses").json()["items"]
    assert [i["text"] for i in items] == ["采分点二"]
    assert items[0]["kind"] == "涵摄"


def test_daily_type_essay_returns_materials(client):
    """type=essay 只下发论述题，且带材料与四段式骨架。"""
    q = client.get("/api/cases/daily?type=essay").json()["question"]
    assert q["qtype"] == "essay"
    assert q["materials"][0]["label"] == "材料一"
    assert q["slot"]["slot"] == 1
    assert "points" not in q and "reference" not in q


def test_daily_type_composite(client):
    q = client.get("/api/cases/daily?type=composite").json()["question"]
    assert q["qtype"] == "composite"
    assert q["slot"]["slot"] == 4
    assert len(q["questions"]) == 2


def test_daily_defaults_to_case(client):
    data = client.get("/api/cases/daily").json()
    assert data["question"]["qtype"] == "case"
    assert data["stats"]["published"] == 1


def test_daily_rejects_unknown_type(client):
    assert client.get("/api/cases/daily?type=essayy").status_code == 422


def test_essay_grade_includes_form_check(client):
    qid = client.get("/api/cases/daily?type=essay").json()["question"]["id"]
    client.post(f"/api/cases/{qid}/answer", json={"answer_text": "写得太少"})
    graded = client.post(f"/api/cases/{qid}/grade", json={"hit_points": [1]}).json()
    assert graded["essay"]["reach"] is False
    assert graded["essay"]["min_chars"] == 600


def test_misses_and_history_filter_by_type(client):
    qid = client.get("/api/cases/daily?type=essay").json()["question"]["id"]
    client.post(f"/api/cases/{qid}/answer", json={"answer_text": "x"})
    client.post(f"/api/cases/{qid}/grade", json={"hit_points": []})
    assert client.get("/api/cases/misses?type=case").json()["items"] == []
    assert client.get("/api/cases/misses?type=essay").json()["items"]
    assert client.get("/api/cases/history?type=essay").json()["items"]
