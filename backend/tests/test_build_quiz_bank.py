import json

from app import db, importer, quiz_bank
from scripts import build_quiz_bank as bqb


def seed(conn, n=3):
    entries = []
    for i in range(1, n + 1):
        entries.append({
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": f"考点{i}",
            "anchor": f"甲实施行为{i}，造成后果{i}，案件事实完整描述",
            "conclusion": f"成立罪名{i}。", "priority": "高频考点",
            "rationale": "高频",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": ["刑法269条"], "note": None, "tts_override": None,
            "tts_text": f"【刑法·考点{i}】结论{i}。"})
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": n, "entries": entries})


def _quiz(**kw):
    data = {"stem": "甲的行为如何定性？",
            "options": ["A. 成立抢劫罪", "B. 成立盗窃罪", "C. 成立抢夺罪", "D. 不构成犯罪"],
            "answer": "A", "analysis": "成立抢劫罪，因当场使用暴力抗拒抓捕。",
            "basis": "刑法269条"}
    data.update(kw)
    return data


def test_check_quiz_accepts_good_question():
    entry = {"conclusion": "成立抢劫罪。"}
    assert bqb.check_quiz(_quiz(), entry) == []


def test_check_quiz_rejects_bad_shapes():
    entry = {"conclusion": "成立抢劫罪。"}
    assert any("选项不足" in e for e in
               bqb.check_quiz(_quiz(options=["A. 甲"]), entry))
    assert any("答案非法" in e for e in bqb.check_quiz(_quiz(answer="E"), entry))
    assert any("解析过短" in e for e in bqb.check_quiz(_quiz(analysis="短"), entry))
    assert any("题干过短" in e for e in bqb.check_quiz(_quiz(stem="短"), entry))
    dup = _quiz(options=["A. 同", "A. 同", "C. 丙", "D. 丁"])
    assert any("重复选项" in e for e in bqb.check_quiz(dup, entry))


def test_check_quiz_detects_answer_mismatch():
    """正确项与条目结论对不上时必须报错（防答案张冠李戴）。"""
    entry = {"conclusion": "构成交通肇事罪，处三年以下有期徒刑。"}
    errs = bqb.check_quiz(_quiz(), entry)
    assert any("无明显对应" in e for e in errs)


def test_check_quiz_accepts_condensed_correct_option():
    """正确项是结论的压缩/同义改写时不应误杀（如「1倍以上5倍以下」）。"""
    entry = {"conclusion": "恶意侵权情节严重的，可适用惩罚性赔偿，倍数为1-5倍。"}
    quiz = _quiz(answer="B", options=["A. 不适用惩罚性赔偿", "B. 1倍以上5倍以下",
                                      "C. 3倍以下", "D. 5倍以上"],
                 analysis="情节严重的恶意侵权适用1至5倍惩罚性赔偿。")
    assert bqb.check_quiz(quiz, entry) == []


def test_similar_two_gram_overlap():
    assert bqb._similar("反补贴针对专项性补贴", "反补贴要件：补贴具有专向性")
    assert not bqb._similar("成立抢劫罪", "适用诉讼时效三年的规定")


def test_same_numbers_matches_numeric_conclusions():
    assert bqb._same_numbers("1倍以上5倍以下", "倍数为1-5倍")
    assert bqb._same_numbers("六个月内分配", "应当在决议作出之日起六个月内进行分配")
    assert not bqb._same_numbers("三个月", "六个月")


def test_check_quiz_accepts_multi_answer():
    entry = {"conclusion": "甲、乙均成立抢劫罪。"}
    quiz = _quiz(answer="AB",
                 options=["A. 甲成立抢劫罪", "B. 乙成立抢劫罪",
                          "C. 甲乙均不构成犯罪", "D. 仅甲构成抢夺罪"])
    assert bqb.check_quiz(quiz, entry) == []


def test_entries_to_process_filters(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, 3)
    quiz_bank.save_question(conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                            entry_id="XF-002", subject="刑法", stem="已有题",
                            options=["A. 甲"], answer="A")
    rows = bqb.entries_to_process(conn, None, None, only_missing=True, limit=0)
    assert [r["id"] for r in rows] == ["XF-001", "XF-003"]
    rows = bqb.entries_to_process(conn, "民法", None, only_missing=False, limit=0)
    assert rows == []
    assert len(bqb.entries_to_process(conn, None, None, False, 2)) == 2
    conn.close()


def test_entries_priority_order(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, 1)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x", "count": 1,
        "entries": [{
            "id": "XF-009", "subject": "刑法", "submodule": "总则", "point": "普通考点",
            "anchor": "甲实施普通行为，造成后果，案件事实完整描述",
            "conclusion": "普通结论。", "priority": "普通", "rationale": "x",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}]})
    rows = bqb.entries_to_process(conn, None, None, False, 0)
    assert rows[0]["id"] == "XF-001" and rows[-1]["id"] == "XF-009"
    conn.close()


def test_peers_for_excludes_self(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    seed(conn, 3)
    entry = {"id": "XF-001", "subject": "刑法", "submodule": "分则-财产犯罪"}
    peers = bqb.peers_for(conn, entry)
    assert [p["point"] for p in peers] == ["考点2", "考点3"]
    conn.close()
