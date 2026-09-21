from app import db, importer, quiz_bank, statute_coverage, statutes


def _entry(eid: str, statutes_refs: list[str]) -> dict:
    return {
        "id": eid, "subject": "刑事法" if eid.startswith("XF") else "民法",
        "submodule": "总则", "point": f"考点{eid}",
        "anchor": "甲实施某行为，造成后果，案件事实完整描述",
        "conclusion": "成立某结论。", "priority": "高频考点", "rationale": "x",
        "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                     "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕或者毁灭罪证而当场使用暴力"}],
        "statutes": statutes_refs, "note": None, "tts_override": None,
        "tts_text": "文本。"}


def test_resolve_law_article_variants():
    assert statutes.resolve_law_article("刑诉法91条") == ("中华人民共和国刑事诉讼法", 91, 0)
    assert statutes.resolve_law_article("刑法287条之二") == ("中华人民共和国刑法", 287, 2)
    assert statutes.resolve_law_article("民法典第1165条")[0] == "中华人民共和国民法典"
    assert statutes.resolve_law_article("无此法第1条") is None
    assert statutes.resolve_law_article("民法典") is None


def test_resolve_law_article_for_amendment_files():
    """刑法修正案（十二）没有「第X条」写法，按「一、二、三、」序号解析后要能定位。"""
    key = "中华人民共和国刑法修正案（十二）"
    assert statutes.resolve_law_article(f"{key}第五条") == (key, 5, 0)
    assert statutes.resolve_law_article(f"{key}第一条") == (key, 1, 0)
    body = statutes.resolve_statute(f"{key}第五条")
    assert body and "行贿罪" in body


def test_coverage_counts_cited_and_covered(tmp_path, monkeypatch):
    """覆盖率口径：条文总数 / 被条目引用 / 被题目覆盖。"""
    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    (law_dir / "中华人民共和国刑法.md").write_text(
        "# 中华人民共和国刑法\n\n"
        "第一条　为了惩罚犯罪，保护人民，根据宪法，制定本法。\n"
        "第二条　中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争，以保卫国家安全。\n"
        "第三条　法律明文规定为犯罪行为的，依照法律定罪处刑。\n",
        encoding="utf-8")
    monkeypatch.setattr(statute_coverage.config, "STATUTE_DIR", law_dir)

    db_path = tmp_path / "cov.db"
    conn = db.connect(db_path)
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": 1,
                                   "entries": [_entry("XF-001", ["刑法第二条"])]})
    quiz_bank.save_question(conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                            subject="刑法", stem="题干足够长的一句话",
                            options=["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
                            answer="A", status="published", basis="中华人民共和国刑法第一条")
    rows = {r["key"]: r for r in statute_coverage.coverage(conn)}
    law = rows["中华人民共和国刑法"]
    assert law["articles"] == 3
    assert law["cited"] == 1          # 条目引用了第二条
    assert law["covered"] == 1        # 题目覆盖了第一条
    assert law["cited_and_covered"] == 0
    assert law["coverage"] == round(1 / 3, 4)
    conn.close()


def test_coverage_counts_only_published_questions(tmp_path, monkeypatch):
    """草稿题不计入覆盖率（用户练不到，且下一轮缺口计算依赖它）。"""
    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    (law_dir / "中华人民共和国刑法.md").write_text(
        "# 中华人民共和国刑法\n\n"
        "第一条　为了惩罚犯罪，保护人民，根据宪法，制定本法。\n"
        "第二条　中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争。\n",
        encoding="utf-8")
    monkeypatch.setattr(statute_coverage.config, "STATUTE_DIR", law_dir)

    conn = db.connect(tmp_path / "cov3.db")
    quiz_bank.save_question(conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                            subject="刑法", stem="题干足够长的一句话",
                            options=["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
                            answer="A", status="draft", basis="中华人民共和国刑法第一条")
    assert statute_coverage.coverage(conn)[0]["covered"] == 0

    conn.execute("UPDATE quizzes SET status='published'")
    conn.commit()
    assert statute_coverage.coverage(conn)[0]["covered"] == 1
    conn.close()


def test_coverage_ignores_unparsable_refs(tmp_path, monkeypatch):
    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    (law_dir / "中华人民共和国刑法.md").write_text(
        "# 中华人民共和国刑法\n第一条　内容。\n", encoding="utf-8")
    monkeypatch.setattr(statute_coverage.config, "STATUTE_DIR", law_dir)

    conn = db.connect(tmp_path / "cov2.db")
    importer.import_payload(conn, {"schema": "fakao-entry/1.0", "status": "final",
                                   "generated_at": "x", "count": 1,
                                   "entries": [_entry("XF-002", ["某不存在的法第3条"])]})
    rows = statute_coverage.coverage(conn)
    assert rows[0]["cited"] == 0
    conn.close()
