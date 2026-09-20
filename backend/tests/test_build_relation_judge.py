import json

from app import db, quiz_bank
from scripts import build_relation_judge as brj

YEAR_ARTICLE = (
    "第九十一条　人民法院审理案件，应当在开庭三日前通知当事人，"
    "并可以要求当事人补充材料。\n"
)
CONVENTION_ARTICLE = (
    "第二条　缔约国对于外交代表，应当给予必要的保护，并可以要求其遵守当地法律。\n"
)
#: 只含「可以」的条文，用于「可以 → 应当」白名单偷换的定向测试
SWAP_ARTICLE = "人民法院审理案件，可以要求当事人补充材料。"


def _write_law(tmp_path, name: str, body: str) -> None:
    (tmp_path / f"{name}.md").write_text(body, encoding="utf-8")


def test_statute_candidates_prioritise_high_weight_subjects(monkeypatch, tmp_path):
    _write_law(tmp_path, "维也纳外交关系公约", CONVENTION_ARTICLE)
    _write_law(tmp_path, "中华人民共和国刑法", YEAR_ARTICLE)
    monkeypatch.setattr(brj.config, "STATUTE_DIR", tmp_path)
    conn = db.connect(tmp_path / "rel.db")
    picked = brj.statute_candidates(conn, max_per_article=2)
    assert [it["subject"] for it in picked] == ["刑法", "三国法"]
    conn.close()


def test_statute_candidates_cap_families_per_article(monkeypatch, tmp_path):
    _write_law(tmp_path, "中华人民共和国刑法", YEAR_ARTICLE)
    monkeypatch.setattr(brj.config, "STATUTE_DIR", tmp_path)
    conn = db.connect(tmp_path / "rel.db")
    capped = brj.statute_candidates(conn, max_per_article=1)
    assert len(capped) == 1 and capped[0]["family"] == "modal"
    full = brj.statute_candidates(conn, max_per_article=0)
    assert len(full) >= 1
    conn.close()


def test_statute_candidates_skip_covered_basis_variant(monkeypatch, tmp_path):
    _write_law(tmp_path, "中华人民共和国刑法", YEAR_ARTICLE)
    monkeypatch.setattr(brj.config, "STATUTE_DIR", tmp_path)
    conn = db.connect(tmp_path / "rel.db")
    assert brj.statute_candidates(conn, max_per_article=2)
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, subject="刑法",
        stem="人民法院审理案件应当通知当事人。", answer="对",
        basis="中华人民共和国刑法第九十一条", variant="modal")
    left = brj.statute_candidates(conn, max_per_article=2)
    assert [it["family"] for it in left] == []      # 唯一词族已出题 → 跳过
    conn.close()


def test_entry_candidates_skip_covered_entry(tmp_db):
    from app import importer

    db_path, _ = tmp_db
    conn = db.connect(db_path)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x", "count": 1,
        "entries": [{
            "id": "XF-001", "subject": "刑法", "submodule": "总则", "point": "追诉时效",
            "anchor": "甲犯罪后经过五年，案件事实完整描述", "conclusion": "应当追诉。",
            "priority": "高频考点", "rationale": "x",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}]})
    assert [it["family"] for it in brj.entry_candidates(conn)] == ["modal"]
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, entry_id="XF-001",
        subject="刑法", stem="甲应当追诉。", answer="对", variant="modal")
    assert brj.entry_candidates(conn) == []
    conn.close()


def test_relation_prompt_lists_whitelist_swaps():
    prompt = brj.relation_prompt("应当立案。", "", "modal")
    assert "应当→可以/无须" in prompt and "只考一个考点" in prompt
    assert "可以" in prompt and "必须" in prompt


def _mock_llm(monkeypatch, payload: dict):
    monkeypatch.setattr(brj.ai, "call_llm",
                        lambda *a, **k: json.dumps(payload, ensure_ascii=False))


def _item():
    return {"law": "中华人民共和国刑法", "no": "第九十一条", "subject": "刑法",
            "family": "modal", "text": SWAP_ARTICLE}


def test_build_one_accepts_whitelisted_swap(monkeypatch):
    _mock_llm(monkeypatch, {"stem": "人民法院审理案件应当要求当事人补充材料。",
                            "answer": "错", "analysis": "原文为可以，非应当。",
                            "basis": "刑诉法第91条"})
    _item_result, quiz, why = brj.build_one(_item())
    assert quiz is not None and why == ""


def test_build_one_rejects_off_whitelist_swap(monkeypatch):
    _mock_llm(monkeypatch, {"stem": "人民法院审理案件撤销补充材料的要求。",
                            "answer": "错", "analysis": "x", "basis": ""})
    _item_result, quiz, why = brj.build_one(_item())
    assert quiz is not None and "不允许" in why


def test_build_one_rejects_new_relation_term_in_true_question(monkeypatch):
    _mock_llm(monkeypatch, {"stem": "人民法院审理案件必须要求当事人补充材料。",
                            "answer": "对", "analysis": "x", "basis": ""})
    _item_result, quiz, why = brj.build_one(_item())
    assert quiz is not None and "原文外关系词" in why


def test_build_one_checks_numbers_inside_relation_stem(monkeypatch):
    _mock_llm(monkeypatch, {"stem": "人民法院审理案件可以提前五日通知当事人。",
                            "answer": "对", "analysis": "x", "basis": ""})
    _item_result, quiz, why = brj.build_one(_item())
    assert quiz is not None and "原文外的数字" in why


def test_parse_rejects_illegal_payload():
    assert brj._parse('{"stem":"人民法院应当通知当事人。","answer":"是"}') is None
    assert brj._parse('{"stem":"太短","answer":"对"}') is None
    assert brj._parse(None) is None
    assert brj._parse("```json\n" + json.dumps(
        {"stem": "人民法院应当通知当事人参加庭审。", "answer": "对"},
        ensure_ascii=False) + "\n```")["answer"] == "对"


def test_basis_of_uses_canonical_law_name():
    assert brj._basis_of({"law": "中华人民共和国刑法", "no": "第九十一条"},
                         {"basis": ""}) == "中华人民共和国刑法第九十一条"
    assert brj._basis_of({"entry_id": "XF-001"}, {"basis": "刑法第5条"}) == "刑法第5条"


def test_counterparts_ignore_number_questions(tmp_db):
    """数字题（variant=number）不参与关系题配对，否则 family='number' 会崩。"""
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, subject="刑法",
        stem="刑事拘留最长三十七日。", answer="对", basis="刑诉法第91条",
        variant="number", status="published")
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, subject="刑法",
        stem="人民法院审理案件应当通知当事人。", answer="对",
        basis="刑诉法第91条", variant="modal", status="published")
    picked = brj.counterpart_candidates(conn)
    assert [it["family"] for it in picked] == ["modal"]
    conn.close()


def test_build_one_reports_unknown_family():
    _item_result, quiz, why = brj.build_one(
        {"law": "中华人民共和国刑法", "no": 91, "subject": "刑法",
         "family": "number", "text": "人民法院审理案件，可以要求补充材料。"})
    assert quiz is None and "未知词族" in why


def test_judge_quiz_pool_mixes_number_and_relation(tmp_db):
    """判断题抽题池：数字题与关系题混排（前端判断题入口无需改动）。"""
    from app import quiz_service

    db_path, _ = tmp_db
    conn = db.connect(db_path)
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, subject="刑法",
        stem="刑事拘留最长三十七日。", answer="对", variant="number",
        status="published")
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, subject="刑法",
        stem="人民法院审理案件应当通知当事人。", answer="对", variant="modal",
        status="published")
    picked = quiz_service.judge_quiz(conn, limit=10)["questions"]
    assert {q["variant"] for q in picked} == {"number", "modal"}
    conn.close()
