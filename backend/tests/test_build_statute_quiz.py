"""法条驱动客观题脚本：依据写法与覆盖率口径。"""
from app import statute_index, statutes
from scripts import build_statute_quiz as bsq


def test_statute_basis_uses_display_name():
    """带 -全文 后缀的法条库主名不能出现在依据里，且要能反查回法条原文。"""
    law = statute_index.load_library()["民营经济促进法-全文"]
    article = law.article(41, 0)
    basis = bsq.statute_basis("民营经济促进法-全文", article)
    assert basis == "中华人民共和国民营经济促进法第四十一条"
    assert statutes.resolve_law_article(basis) == ("民营经济促进法-全文", 41, 0)


def test_statute_basis_keeps_plain_law_names():
    law = statute_index.load_library()["中华人民共和国刑法"]
    article = law.article(269, 0)
    assert bsq.statute_basis("中华人民共和国刑法", article) == \
        "中华人民共和国刑法第二百六十九条"


def test_target_candidates_fills_gap_per_law(tmp_db, tmp_path, monkeypatch):
    """--target-ratio 按每部法缺口反推：10 条法、已覆盖 5 条、目标 80% → 还差 3 条。"""
    from app import config, db, quiz_bank

    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    body = "本条为测试条文，正文长度需超过二十个字符以便通过解析过滤。"
    (law_dir / "中华人民共和国刑法.md").write_text(
        "# 中华人民共和国刑法\n\n" + "".join(
            f"第{statute_index.int2cn(i)}条　{body}\n" for i in range(1, 11)),
        encoding="utf-8")
    monkeypatch.setattr(config, "STATUTE_DIR", law_dir)
    statute_index.clear_cache()
    statutes._LAW_FILE_CACHE.clear()

    db_path, _ = tmp_db
    conn = db.connect(db_path)
    for i in range(1, 6):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, subject="刑法",
            stem=f"题{i}", options=["A. 甲", "B. 乙"], answer="A", analysis="解析",
            basis=f"中华人民共和国刑法第{statute_index.int2cn(i)}条",
            status="published")
    picked = bsq.target_candidates(conn, 0.8)
    assert len(picked) == 3
    assert {p["law"] for p in picked} == {"中华人民共和国刑法"}
    assert {p["no"] for p in picked} == {6, 7, 8}      # 取未覆盖的前 3 条
    assert bsq.target_candidates(conn, 0.1) == []       # 已达标：10% → 需要 1 条，已覆盖 5 条
    conn.close()
