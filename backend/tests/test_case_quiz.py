"""每日案例服务层测试：选题、下发脱敏、作答、采分点判分。"""
import json

from app import case_quiz, db

POINTS = [
    {"no": 1, "kind": "结论", "text": "表见代理成立", "statutes": []},
    {"no": 2, "kind": "依据", "text": "依据民法典第172条",
     "statutes": ["民法典第172条"]},
    {"no": 3, "kind": "涵摄", "text": "甲持空白合同构成权利外观",
     "statutes": []},
]


def seed(conn, loc="case_00001", status="published", subject="民法"):
    cur = conn.execute(
        "INSERT INTO case_questions (case_source, case_loc, subject, stem, questions,"
        " points, reference, status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("人民法院案例库", loc, subject, "甲持空白合同以乙名义签约，丙不知情。",
         json.dumps(["丙能否要求乙承担责任？"], ensure_ascii=False),
         json.dumps(POINTS, ensure_ascii=False), "乙应承担责任。", status, "2026-09-20"))
    conn.commit()
    return cur.lastrowid


def test_pick_daily_returns_none_when_empty(tmp_db):
    conn = db.connect(tmp_db[0])
    assert case_quiz.pick_daily(conn, "2026-09-20") is None
    conn.close()


def test_pick_daily_ignores_draft(tmp_db):
    conn = db.connect(tmp_db[0])
    seed(conn, status="draft")
    assert case_quiz.pick_daily(conn, "2026-09-20") is None
    conn.close()


def test_pick_daily_stable_and_rotates(tmp_db):
    conn = db.connect(tmp_db[0])
    seed(conn, "case_00001")
    seed(conn, "case_00002")
    seed(conn, "case_00003")
    first = case_quiz.pick_daily(conn, "2026-09-20")
    again = case_quiz.pick_daily(conn, "2026-09-20")
    assert first["id"] == again["id"]
    conn.close()


def test_public_payload_hides_answer(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    payload = case_quiz.public_payload(case_quiz.question_by_id(conn, qid))
    assert "points" not in payload and "reference" not in payload
    assert payload["stem"] and payload["questions"]
    conn.close()


def test_submit_answer_creates_attempt_and_reveals_points(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    res = case_quiz.submit_answer(conn, qid, "我的答案", 120, "write")
    assert res["attempt_id"] > 0
    assert len(res["points"]) == 3
    row = conn.execute("SELECT * FROM case_attempts WHERE id=?",
                       (res["attempt_id"],)).fetchone()
    assert row["mode"] == "write" and row["duration_sec"] == 120
    conn.close()


def test_grade_scores_and_lists_missed(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    res = case_quiz.grade(conn, qid, [1, 2])
    assert res["score"] == 67 and res["total"] == 3 and res["hit"] == [1, 2]
    assert [m["no"] for m in res["missed"]] == [3]
    assert res["reference"] == "乙应承担责任。"
    conn.close()


def test_grade_reports_by_kind(tmp_db):
    """按维度给出命中情况，用于看出「结论对但依据缺」。"""
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    res = case_quiz.grade(conn, qid, [1])
    got = {d["kind"]: (d["hit"], d["total"]) for d in res["by_kind"]}
    assert got == {"结论": (1, 1), "依据": (0, 1), "涵摄": (0, 1)}
    assert [m["kind"] for m in res["missed"]] == ["依据", "涵摄"]
    conn.close()


def test_grade_ignores_invalid_point_numbers(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    res = case_quiz.grade(conn, qid, [1, 99, -1])
    assert res["hit"] == [1] and res["score"] == 33
    conn.close()


def test_grade_full_score(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "listen")
    res = case_quiz.grade(conn, qid, [1, 2, 3])
    assert res["score"] == 100 and res["missed"] == []
    conn.close()


def test_missed_points_carry_statute_links(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    res = case_quiz.grade(conn, qid, [])
    point = next(m for m in res["missed"] if m["links"])
    link = point["links"][0]
    assert link["law"] == "民法典" and link["no"] == 172
    assert link["url"] == "/statutes?law=民法典&no=172"
    conn.close()


def test_statute_link_returns_none_for_bad_ref():
    assert case_quiz.statute_link("没有条号") is None
    assert case_quiz.statute_link("") is None


def test_statute_link_skips_laws_outside_library():
    """法条库没收录的法（如个人信息保护法）不给链接，避免前端撞 404。"""
    assert case_quiz.statute_link("个人信息保护法第11条") is None
    assert case_quiz.statute_link("民法典第172条") is not None


def test_history_reports_misses(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    case_quiz.grade(conn, qid, [1])
    items = case_quiz.history(conn)
    assert len(items) == 1
    assert items[0]["score"] == 33 and len(items[0]["missed"]) == 2
    conn.close()


def test_stats_summary(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    case_quiz.grade(conn, qid, [1, 2, 3])
    s = case_quiz.stats_summary(conn)
    assert s["attempts"] == 1 and s["published"] == 1
    assert s["by_subject"][0]["subject"] == "民法"
    conn.close()


def test_pick_daily_prefers_unattempted(tmp_db):
    conn = db.connect(tmp_db[0])
    a = seed(conn, "case_00001")
    seed(conn, "case_00002")
    case_quiz.submit_answer(conn, a, "答", 10, "write")
    picked = case_quiz.pick_daily(conn, "2026-09-20")
    assert picked["id"] != a
    conn.close()


def test_misses_pool_aggregates_by_text(tmp_db):
    """复盘池：同一采分点跨题聚合，未命中的才进池。"""
    conn = db.connect(tmp_db[0])
    a = seed(conn, "case_00001")
    b = seed(conn, "case_00002")
    for qid, hits in ((a, [1]), (b, [1, 2])):
        case_quiz.submit_answer(conn, qid, "答", 10, "write")
        case_quiz.grade(conn, qid, hits)
    pool = case_quiz.misses(conn)
    by_text = {it["text"]: it for it in pool}
    assert "表见代理成立" not in by_text            # 两次都答到，不进池
    assert by_text["依据民法典第172条"]["missed"] == 1
    assert by_text["依据民法典第172条"]["asked"] == 2
    assert by_text["甲持空白合同构成权利外观"]["missed"] == 2
    assert by_text["甲持空白合同构成权利外观"]["links"] == []
    conn.close()


def test_misses_pool_filters_by_subject(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn, "case_00001", subject="民法")
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    case_quiz.grade(conn, qid, [])
    assert case_quiz.misses(conn, subject="民法")
    assert case_quiz.misses(conn, subject="刑法") == []
    conn.close()


def test_public_payload_carries_skeleton_and_slot(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn, subject="行政法")
    payload = case_quiz.public_payload(case_quiz.question_by_id(conn, qid))
    assert payload["slot"]["slot"] == 5
    assert any("主体" in s for s in payload["skeleton"])
    conn.close()


MATERIAL = ("宪法是国家的根本法，是治国安邦的总章程，具有最高的法律效力，"
            "坚持依宪治国、依宪执政是全面依法治国的首要任务。")


def seed_essay(conn, loc="essay-001", subject="理论法", status="published"):
    cur = conn.execute(
        "INSERT INTO case_questions (case_source, case_loc, subject, qtype, stem,"
        " questions, points, materials, reference, status, created_at)"
        " VALUES ('法治思想-核心论述',? ,?,'essay','请阅读材料回答。',?,?,?,?,?,"
        "'2026-09-20')",
        (loc, subject,
         json.dumps(["谈谈你的认识。"], ensure_ascii=False),
         json.dumps([{"no": 1, "kind": "总论点", "text": "依宪治国是首要任务",
                      "statutes": []}], ensure_ascii=False),
         json.dumps([{"label": "材料一", "text": MATERIAL}], ensure_ascii=False),
         "提纲：总论点—理论—材料—措施。", status))
    conn.commit()
    return cur.lastrowid


def seed_composite(conn, loc="case_09999"):
    cur = conn.execute(
        "INSERT INTO case_questions (case_source, case_loc, subject, qtype, stem,"
        " questions, points, reference, status, created_at) VALUES"
        " ('人民法院案例库',?,'民法','composite','长案情。',?,?,'提纲。','published',"
        "'2026-09-20')",
        (loc,
         json.dumps(["甲能否请求乙付款？", "本案由哪个法院管辖？"], ensure_ascii=False),
         json.dumps([
             {"no": 1, "qno": 1, "kind": "结论", "text": "可以请求付款",
              "statutes": []},
             {"no": 2, "qno": 2, "kind": "程序", "text": "由合同履行地法院管辖",
              "statutes": []}], ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def test_pick_daily_filters_by_type(tmp_db):
    """今日案例只取案例分析题，论述题/综合大案例各有各的入口。"""
    conn = db.connect(tmp_db[0])
    case_id = seed(conn, "case_00001")
    essay_id = seed_essay(conn)
    composite_id = seed_composite(conn)
    assert case_quiz.pick_daily(conn, "2026-09-20")["id"] == case_id
    assert case_quiz.pick_daily(conn, "2026-09-20", "essay")["id"] == essay_id
    assert case_quiz.pick_daily(conn, "2026-09-20", "composite")["id"] == composite_id
    conn.close()


def test_public_payload_carries_qtype_materials_and_spec(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed_essay(conn)
    payload = case_quiz.public_payload(case_quiz.question_by_id(conn, qid))
    assert payload["qtype"] == "essay"
    assert payload["materials"][0]["label"] == "材料一"
    assert payload["spec"]["min_chars"] == 600
    assert payload["slot"]["slot"] == 1
    assert any("总论点" in s for s in payload["skeleton"])
    conn.close()


def test_essay_metrics_flags_short_answer():
    m = case_quiz.essay_metrics("观点：依宪治国是首要任务。", [{"text": MATERIAL}])
    assert m["reach"] is False and m["copied"] is False
    assert any("字数不足" in v for v in m["verdict"])


def test_essay_metrics_flags_copied_material():
    m = case_quiz.essay_metrics(MATERIAL * 8, [{"text": MATERIAL}])
    assert m["copied"] is True and m["copy_ratio"] > m["copy_limit"]
    assert any("照搬" in v for v in m["verdict"])


def test_essay_metrics_passes_with_own_words():
    body = "".join(
        f"第{i}点，坚持党的领导是全面依法治国的根本保证，必须落实到立法、执法、"
        "司法、守法各个环节。" for i in range(30))
    m = case_quiz.essay_metrics(body, [{"text": MATERIAL}])
    assert m["reach"] is True and m["copied"] is False and m["verdict"] == []


def test_grade_returns_essay_form_check(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed_essay(conn)
    case_quiz.submit_answer(conn, qid, "写得太短", 60, "write")
    res = case_quiz.grade(conn, qid, [1])
    assert res["essay"]["chars"] == 4 and res["essay"]["reach"] is False
    assert res["score"] == 100
    conn.close()


def test_grade_has_no_essay_block_for_case(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed(conn)
    case_quiz.submit_answer(conn, qid, "答", 10, "write")
    assert case_quiz.grade(conn, qid, [1])["essay"] is None
    conn.close()


def test_composite_points_carry_question_number(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = seed_composite(conn)
    res = case_quiz.submit_answer(conn, qid, "答", 10, "write")
    assert {p["qno"] for p in res["points"]} == {1, 2}
    assert case_quiz.question_by_id(conn, qid)["qtype"] == "composite"
    conn.close()


def test_stats_summary_filters_by_type(tmp_db):
    conn = db.connect(tmp_db[0])
    essay_id = seed_essay(conn)
    seed(conn, "case_00001")
    case_quiz.submit_answer(conn, essay_id, "答", 10, "write")
    case_quiz.grade(conn, essay_id, [1])
    assert case_quiz.stats_summary(conn, "essay")["published"] == 1
    assert case_quiz.stats_summary(conn, "essay")["attempts"] == 1
    assert case_quiz.stats_summary(conn, "case")["attempts"] == 0
    assert case_quiz.stats_summary(conn)["published"] == 2
    conn.close()


def test_history_filters_by_type(tmp_db):
    conn = db.connect(tmp_db[0])
    essay_id = seed_essay(conn)
    case_quiz.submit_answer(conn, essay_id, "答", 10, "write")
    case_quiz.grade(conn, essay_id, [1])
    assert case_quiz.history(conn, qtype="essay")[0]["qtype"] == "essay"
    assert case_quiz.history(conn, qtype="case") == []
    conn.close()
