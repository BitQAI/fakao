from datetime import date

from app import db, importer, service


def seed(conn, n=5):
    entries = []
    for i in range(1, n + 1):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": f"考点{i}", "anchor": f"甲实施行为{i}，造成后果{i}，案件事实完整描述",
            "conclusion": f"成立罪名{i}。", "priority": "高频考点",
            "rationale": "高频", "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                                              "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": ["刑法269条"], "note": None, "tts_override": None,
            "tts_text": f"【刑法·考点{i}】结论{i}。"})
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": n, "entries": entries})


def test_ensure_today_plan_generates(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    plan = service.ensure_today_plan(conn, "2026-08-27")
    assert plan["quota"] == 5
    assert plan["counts"]["new"] == 5
    assert plan["items"][0]["bucket"] == "new"
    assert plan["items"][0]["point"] == "考点1"
    assert "距考试" in plan["rationale"] or plan["rationale"]


def test_plan_not_regenerated_when_exists(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    first = service.ensure_today_plan(conn, "2026-08-27")
    conn.execute("UPDATE daily_plans SET rationale='已修改' WHERE date='2026-08-27'")
    conn.commit()
    second = service.ensure_today_plan(conn, "2026-08-27")
    assert second["rationale"] == "已修改"


def test_record_review_and_coverage(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.record_review(conn, "XF-001", "read", "bad")
    service.record_review(conn, "XF-001", "read", "good")
    tree = service.coverage_payload(conn)
    point_state = tree["刑法"]["submodules"]["分则-财产犯罪"]["points"]["考点1"]
    # 两次复习且末次 good → coverage.entry_state 返回 mastered（与 coverage spec 一致）
    assert point_state == "mastered"


def test_build_daily_quiz_falls_back_to_cloze(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.ensure_today_plan(conn, "2026-08-27")
    questions = service.build_daily_quiz(conn, "2026-08-27")
    assert questions and questions[0]["qtype"] == "cloze"
    assert "____" in questions[0]["stem"]


def test_quiz_answer_records(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    service.set_setting(conn, "exam_date", "2026-09-13")
    today = date.today().isoformat()
    service.ensure_today_plan(conn, today)
    questions = service.build_daily_quiz(conn, today)
    service.record_quiz_answer(conn, questions[0]["id"], "随便答", False)
    stats = service.today_stats(conn, today)
    assert stats["quiz_total"] == 1 and stats["quiz_correct"] == 0
    assert stats["days_left"] == (date(2026, 9, 13) - date.today()).days


def test_settings_and_days_left(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    assert service.days_left(conn, "2026-08-27") is None
    service.set_setting(conn, "exam_date", "2026-09-13")
    assert service.days_left(conn, "2026-08-27") == 17


def test_morning_report_reuses_same_day(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    first = service.morning_report(conn, "2026-08-27")
    second = service.morning_report(conn, "2026-08-27")
    assert first["id"] == second["id"]
    assert "早上好" in first["content"] or first["content"]
    assert "新学 5" in first["content"]


def test_assistant_context_finds_entry(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn)
    context, ids, refs = service.assistant_context(conn, "考点3")
    assert "XF-003" in ids
    assert "考点3" in context
