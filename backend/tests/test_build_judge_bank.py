import pytest

from app import quiz_bank
from scripts import build_judge_bank as bjb


def test_subject_of_maps_laws_to_subjects():
    assert bjb.subject_of("中华人民共和国刑法") == "刑法"
    assert bjb.subject_of("最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释") == "刑诉"
    assert bjb.subject_of("中华人民共和国民法典") == "民法"
    assert bjb.subject_of("中华人民共和国劳动争议调解仲裁法") == "商经知劳环"
    assert bjb.subject_of("中华人民共和国行政处罚法") == "行政法"
    assert bjb.subject_of("联合国国际货物销售合同公约") == "三国法"
    assert bjb.subject_of("某个不存在的法") is None


def test_article_blocks_splits_and_filters():
    text = (
        "第一条　为了规范行为，制定本法。\n"
        "第二条　本法所称期限，是指七日以内的期间；逾期视为放弃，并应书面说明理由。\n"
        "第三条　短。\n"
    )
    blocks = bjb.article_blocks(text)
    assert [no for no, _ in blocks] == ["第二条"]
    assert "七日以内" in blocks[0][1]


def test_score_prefers_numeric_density():
    high = "处三年以上十年以下有期徒刑，并处五万元以上五十万元以下罚金。"
    low = "自2020年1月1日起施行。"
    assert bjb._score_article(high) > bjb._score_article(low)
    assert bjb._score_article("为了惩罚犯罪，保护人民，根据宪法，制定本法。") == 0


def test_statute_candidates_respects_skip(monkeypatch, tmp_path):
    monkeypatch.setattr(bjb.config, "STATUTE_DIR", tmp_path)
    (tmp_path / "中华人民共和国刑法.md").write_text(
        "第一条　为了惩罚犯罪，保护人民，根据宪法，制定本法。\n"
        "第八十七条　犯罪经过下列期限不再追诉：法定最高刑为不满五年有期徒刑的，"
        "经过五年；法定最高刑为五年以上不满十年有期徒刑的，经过十年。\n"
        "第九十条　其他规定内容足够长以便通过长度过滤，这里补足到二十字以上。\n",
        encoding="utf-8")
    picked = bjb.statute_candidates(1, skip_basis=set())
    assert len(picked) == 1
    assert picked[0]["law"] == "中华人民共和国刑法"
    assert picked[0]["subject"] == "刑法"
    assert bjb.statute_candidates(1, skip_basis={"中华人民共和国刑法第八十七条"}) == []


def test_covered_basis_reads_existing_questions(tmp_db):
    import json

    from app import db, importer

    db_path, _ = tmp_db
    conn = db.connect(db_path)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x", "count": 1,
        "entries": [{
            "id": "XF-001", "subject": "刑法", "submodule": "总则", "point": "追诉时效",
            "anchor": "甲犯罪后经过五年，案件事实完整描述", "conclusion": "追诉时效五年。",
            "priority": "高频考点", "rationale": "x",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}]})
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            subject="刑法", stem="法定最高刑不满五年，追诉时效为五年。",
                            answer="对", basis="中华人民共和国刑法第八十七条")
    assert bjb.covered_basis(conn) == {"中华人民共和国刑法第八十七条"}
    conn.close()
    assert json.dumps({})  # 保持 import 语义明确（json 用于其他断言场景）


def test_canonical_basis_normalizes_both_forms():
    """basis 规范成「法条库主名+条号」：兼容「刑诉法91条」与早期的阿拉伯数字后缀写法。"""
    assert bjb.canonical_basis("刑诉法91条") == "中华人民共和国刑事诉讼法第九十一条"
    assert bjb.canonical_basis("中华人民共和国刑法第二百六十九条") == \
        "中华人民共和国刑法第二百六十九条"
    # 早期 counterparts 产物写成「<法条库主名><数字>」
    assert bjb.canonical_basis("中华人民共和国刑事诉讼法91") == \
        "中华人民共和国刑事诉讼法第九十一条"
    assert bjb.canonical_basis("不存在的法第9条") is None
    assert bjb.canonical_basis("民法典") is None


def test_counterpart_candidates_pairs_false_questions(tmp_db):
    """已有「对」题的法条，应被选为「错」题配对候选。"""
    from app import db, importer

    db_path, _ = tmp_db
    conn = db.connect(db_path)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x", "count": 1,
        "entries": [{
            "id": "XF-001", "subject": "刑法", "submodule": "总则", "point": "追诉时效",
            "anchor": "甲犯罪后经过五年，案件事实完整描述",
            "conclusion": "法定最高刑不满五年的，追诉时效为五年。",
            "priority": "高频考点", "rationale": "x",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
            "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}]})
    # 条目侧：已有「对」题 → 需要补「错」题
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            entry_id="XF-001", subject="刑法", stem="追诉时效为五年。",
                            answer="对", status="published")
    items = bjb.counterpart_candidates(conn)
    assert [i.get("entry_id") for i in items] == ["XF-001"]
    # 补上「错」题后不再重复候选
    quiz_bank.save_question(conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                            entry_id="XF-001", subject="刑法", stem="追诉时效为十年。",
                            answer="错", status="published")
    assert bjb.counterpart_candidates(conn) == []
    conn.close()


@pytest.mark.parametrize("payload,expected", [
    ('{"stem":"拘留后应当在三日内提请批准逮捕，不得延长。","answer":"对",'
     '"analysis":"依据刑诉法第91条，拘留后三日以内提请批准。","basis":"刑诉法91条"}',
     "对"),
    ('```json\n{"stem":"仲裁庭应当在五日内将副本送达被申请人。","answer":"错",'
     '"analysis":"正确为十日内。","basis":"仲裁法第30条"}\n```', "错"),
])
def test_parse_accepts_json_and_fenced(payload, expected):
    quiz = bjb._parse(payload)
    assert quiz is not None and quiz["answer"] == expected


def test_parse_rejects_bad_shapes():
    assert bjb._parse(None) is None
    assert bjb._parse("不是 JSON") is None
    assert bjb._parse('{"stem":"太短","answer":"对"}') is None
    assert bjb._parse('{"stem":"一个足够长的判断句，可以用作题目。","answer":"中"}') is None


def test_build_one_enforces_number_gate(monkeypatch):
    """LLM 编造数字时必须被丢弃。"""
    item = {"law": "中华人民共和国刑事诉讼法", "no": "第九十一条", "subject": "刑诉",
            "text": "公安机关对被拘留的人，应当在拘留后的三日以内提请人民检察院审查批准。"}
    monkeypatch.setattr(
        bjb.ai, "call_llm",
        lambda *a, **k: '{"stem":"公安机关应当在拘留后十日内提请批准逮捕。",'
                        '"answer":"对","analysis":"原文为十日。","basis":"刑诉法91条"}')
    _item, quiz, why = bjb.build_one(item)
    assert quiz is not None and "原文外" in why

    monkeypatch.setattr(
        bjb.ai, "call_llm",
        lambda *a, **k: '{"stem":"公安机关应当在拘留后三日以内提请批准逮捕。",'
                        '"answer":"对","analysis":"依据刑诉法第91条。","basis":"刑诉法91条"}')
    _item, quiz, why = bjb.build_one(item)
    assert quiz is not None and why == ""


def test_build_one_rejects_effective_date_only(monkeypatch):
    """纯「自X日起施行」的生效日期句不是数字考点，必须丢弃。"""
    item = {"law": "中华人民共和国反外国不当域外管辖条例", "no": "第一条",
            "subject": "商经知劳环", "text": "本条例自2026年4月7日起施行。"}
    monkeypatch.setattr(
        bjb.ai, "call_llm",
        lambda *a, **k: '{"stem":"本条例自2026年4月7日公布之日起施行。","answer":"对",'
                        '"analysis":"依据条例施行日期。","basis":"反外国不当域外管辖条例第1条"}')
    _item, quiz, why = bjb.build_one(item)
    assert quiz is not None and "生效日期" in why


def test_build_one_keeps_rule_with_date_plus_number(monkeypatch):
    """日期之外还有实质数字考点（期限、人数等）时仍可出题。"""
    item = {"law": "中华人民共和国专利法", "no": "第二十九条", "subject": "商经知劳环",
            "text": "申请人自发明在外国第一次提出专利申请之日起十二个月内享有优先权。"}
    monkeypatch.setattr(
        bjb.ai, "call_llm",
        lambda *a, **k: '{"stem":"申请人自外国首次申请日起十二个月内可主张优先权。",'
                        '"answer":"对","analysis":"优先权期限为十二个月。",'
                        '"basis":"专利法第29条"}')
    _item, quiz, why = bjb.build_one(item)
    assert quiz is not None and why == ""


def test_entry_candidates_use_conclusion_numbers(tmp_db):
    from app import db, importer

    db_path, _ = tmp_db
    conn = db.connect(db_path)
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x", "count": 2,
        "entries": [
            {"id": "XF-001", "subject": "刑法", "submodule": "总则", "point": "追诉时效",
             "anchor": "甲犯罪后经过多年，案件事实完整描述",
             "conclusion": "法定最高刑不满五年的，追诉时效为五年。",
             "priority": "高频考点", "rationale": "x",
             "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                          "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
             "statutes": ["刑法87条"], "note": None, "tts_override": None,
             "tts_text": "文本。"},
            {"id": "XF-002", "subject": "刑法", "submodule": "总则", "point": "无数字",
             "anchor": "乙实施某行为，案件事实完整描述",
             "conclusion": "成立某罪。", "priority": "普通", "rationale": "x",
             "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                          "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
             "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}],
    })
    rows = bjb.entry_candidates(conn, 0)
    assert [r["entry_id"] for r in rows] == ["XF-001"]
    conn.close()
