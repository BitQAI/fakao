"""入口覆盖审计：四个入口的可达集合必须等于全量法条驱动题。"""
from app import config, db, quiz_bank, statute_index, statutes
from scripts import audit_quiz_entrypoints as audit

LAW = """# 中华人民共和国刑法

第一条　为了惩罚犯罪，保护人民，根据宪法，制定本法。
第二条　中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争，以保卫国家安全。
"""


def test_all_entries_reach_every_statute_question(tmp_db, tmp_path, monkeypatch):
    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    (law_dir / "中华人民共和国刑法.md").write_text(LAW, encoding="utf-8")
    monkeypatch.setattr(config, "STATUTE_DIR", law_dir)
    statute_index.clear_cache()
    statutes._LAW_FILE_CACHE.clear()

    conn = db.connect(tmp_db[0])
    for i in range(1, 3):
        quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
            subject="刑法", stem=f"法条题{i}", options=["A. 甲", "B. 乙"],
            answer="A", analysis="解析",
            basis=f"中华人民共和国刑法第{statute_index.int2cn(i)}条",
            status="published")
    # 草稿不算（用户练不到）
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
        subject="刑法", stem="草稿题", options=["A. 甲"], answer="A",
        analysis="x", basis="中华人民共和国刑法第二条", status="draft")

    result = audit.audit(conn)
    conn.close()
    assert result["total"] == 2
    assert result["ok"] is True
    assert {r["entry"] for r in result["entries"]} == {
        "自测（今日）", "看背", "听学", "法条页"}
    assert all(r["missing"] == 0 for r in result["entries"])
