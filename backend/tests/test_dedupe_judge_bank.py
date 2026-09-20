"""去重脚本单测：四条规则各自生效，且不同法的同句式不误伤。"""
from app import db, quiz_bank
from scripts import dedupe_judge_bank as djb


def _seed(conn, rows):
    """直插：绕开 save_question 的幂等去重（本测试要造出重复行）。"""
    for stem, answer, basis, analysis in rows:
        conn.execute(
            "INSERT INTO quizzes (entry_id, subject, point, qtype, origin, stem,"
            " options, answer, analysis, basis, variant, status, text_hash, created_at)"
            " VALUES (NULL,'刑诉','考点','judge','judge',?,'[]',?,?,?,?, 'published',"
            " ?, '2026-09-20T10:00:00')",
            (stem, answer, analysis, basis, "number",
             db.question_hash(stem, answer)))
    conn.commit()


def test_r1_exact_duplicate_archived(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _seed(conn, [
        ("刑事拘留最长三十七日。", "对", "刑诉法第91条", "解析短"),
        ("刑事拘留最长三十七日。", "对", "刑诉法第91条", "解析更长一些的内容"),
    ])
    items = djb.plan(conn)
    assert [i["rule"] for i in items] == ["R1_完全重复"]
    assert djb.apply(conn, items) == 1
    kept = conn.execute("SELECT analysis FROM quizzes WHERE status='published'").fetchone()
    assert kept["analysis"] == "解析更长一些的内容"     # 保留解析更长的
    conn.close()


def test_r2_same_basis_similar_archived(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _seed(conn, [
        ("贪污数额在三万元以上不满二十万元的，属数额较大。", "对", "刑法第383条", "a"),
        ("贪污数额在三万元以上不满二十万元的，应认定为数额较大。", "对", "刑法第383条", "b"),
    ])
    items = djb.plan(conn)
    assert len(items) == 1 and items[0]["rule"].startswith("R")
    assert djb.apply(conn, items) == 1
    conn.close()


def test_r3_same_law_template_archived_but_other_law_kept(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _seed(conn, [
        ("本公约在奥地利联邦外交部签署的截止日期为1950年2月12日。", "对",
         "维也纳外交关系公约第五十条", "a"),
        ("本公约在奥地利联邦外交部签署的截止日期为1951年3月13日。", "对",
         "维也纳外交关系公约第五十一条", "b"),
        ("本公约在奥地利联邦外交部签署的截止日期为1952年4月14日。", "对",
         "维也纳领事关系公约第五十二条", "c"),   # 不同法 → 保留
    ])
    items = djb.plan(conn)
    assert [i["rule"] for i in items] == ["R3_同法模板化"]
    djb.apply(conn, items)
    left = conn.execute(
        "SELECT basis FROM quizzes WHERE status='published'").fetchall()
    assert len(left) == 2
    assert any("领事关系公约" in r["basis"] for r in left)
    conn.close()


def test_r4_same_basis_excess_archived(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _seed(conn, [
        ("人民法院应当在七日内决定是否立案。", "对", "民诉法第126条", "a"),
        ("人民法院应当在七日内决定立案与否。", "对", "民诉法第126条", "b"),
        ("人民法院应当在十五日内决定是否立案。", "对", "民诉法第126条", "c"),
    ])
    items = djb.plan(conn)
    assert len(items) == 2                       # 同源同答案只留一题
    assert all(i["rule"] in ("R2_同源近似", "R4_同源超额") for i in items)
    djb.apply(conn, items)
    assert conn.execute(
        "SELECT COUNT(*) FROM quizzes WHERE status='published'").fetchone()[0] == 1
    conn.close()


def test_true_false_pair_is_kept(tmp_db):
    """同一条文的「对」「错」配对是设计，不应被去重。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _seed(conn, [
        ("刑事拘留最长三十七日。", "对", "刑诉法第91条", "a"),
        ("刑事拘留最长十五日。", "错", "刑诉法第91条", "b"),
    ])
    assert djb.plan(conn) == []
    conn.close()


def test_archived_rows_are_ignored(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _seed(conn, [
        ("刑事拘留最长三十七日。", "对", "刑诉法第91条", "a"),
        ("刑事拘留最长三十七日。", "对", "刑诉法第91条", "b"),
    ])
    items = djb.plan(conn)
    djb.apply(conn, items)
    assert djb.plan(conn) == []                 # 已归档的题不再参与
    conn.close()
