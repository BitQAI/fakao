"""法条卡池：四入口共用、未看过优先、按条查询、听学文本。"""
from app import config, db, importer, quiz_bank, statute_cards, statute_index, statutes

LAW = """# 中华人民共和国刑法

第一条　为了惩罚犯罪，保护人民，根据宪法，制定本法。
第二条　中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争，以保卫国家安全。
第三条　法律明文规定为犯罪行为的，依照法律定罪处刑；法律没有明文规定的，不得定罪处刑。
"""


def _law_dir(tmp_path):
    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    (law_dir / "中华人民共和国刑法.md").write_text(LAW, encoding="utf-8")
    return law_dir


def _seed(conn, n_statute: int = 3) -> list[int]:
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x",
        "count": 1,
        "entries": [{
            "id": "XF-001", "subject": "刑法", "submodule": "总则", "point": "追诉时效",
            "anchor": "甲实施行为，案件事实完整描述", "conclusion": "成立结论。",
            "priority": "高频考点", "rationale": "x",
            "sources": [{"type": "高频", "ref": "a.md", "loc": "犯盗窃、诈骗、抢夺罪而当场使用暴力的情形"}],
            "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}]})
    ids = []
    for i in range(n_statute):
        ids.append(quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
            subject="刑法", stem=f"法条题{i}：某行为应如何定性？",
            options=["A. 甲", "B. 乙"], answer="A", analysis=f"解析{i}",
            basis=f"中华人民共和国刑法第{statute_index.int2cn(i + 1)}条",
            status="published"))
    # 条目派生题：不属于法条卡池
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-001",
        subject="刑法", stem="条目题：非池内内容", options=["A. 甲"], answer="A",
        analysis="x", status="published")
    return ids


def _prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATUTE_DIR", _law_dir(tmp_path))
    statute_index.clear_cache()
    statutes._LAW_FILE_CACHE.clear()


def test_pool_only_has_statute_driven_questions(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    _seed(conn)
    cards = statute_cards.pool(conn, limit=10)
    assert len(cards) == 3                       # 条目派生题不进池
    assert {c["kind"] for c in cards} == {"statute"}
    assert all(c["basis"] and c["article_text"] for c in cards)
    conn.close()


def test_unseen_first_then_seen_last(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    ids = _seed(conn)
    statute_cards.mark_seen(conn, ids[0], "read")

    cards = statute_cards.pool(conn, mode="read", limit=10)
    assert cards[-1]["quiz_id"] == ids[0]         # 看过的排最后
    assert cards[0]["unseen"] is True
    only_unseen = statute_cards.pool(conn, mode="read", limit=10, unseen_only=True)
    assert ids[0] not in {c["quiz_id"] for c in only_unseen}
    # 另一个 mode 互不影响（听过 ≠ 看过）
    assert len(statute_cards.pool(conn, mode="listen", limit=10, unseen_only=True)) == 3
    conn.close()


def test_pool_repeated_rounds_can_exhaust_all(tmp_db, tmp_path, monkeypatch):
    """连续取队列（每次 1 张并标记看过）能取到全部法条题 —— 「完整覆盖」的可验证形式。"""
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    _seed(conn)
    taken = []
    for _ in range(5):
        card = statute_cards.pool(conn, mode="read", limit=1)[0]
        taken.append(card["quiz_id"])
        statute_cards.mark_seen(conn, card["quiz_id"], "read")
    assert len(set(taken)) == 3 and len(taken) == 5   # 3 张全部取到，之后重复也稳定
    conn.close()


def test_by_article_and_listen_text(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    _seed(conn)
    hit = statute_cards.by_article(conn, "中华人民共和国刑法", 1, 0)
    assert len(hit) == 1 and hit[0]["no"] == 1
    assert statute_cards.by_article(conn, "中华人民共和国刑法", 9, 0) == []

    text = statute_cards.listen_text(hit[0])
    assert "法条依据：中华人民共和国刑法第一条" in text
    assert "条文原文：" in text and "答案：A" in text and "解析：解析0" in text
    conn.close()


def test_stats_reports_pool_and_progress(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    ids = _seed(conn)
    statute_cards.mark_seen(conn, ids[0], "listen")
    assert statute_cards.stats(conn) == {"total": 3,
                                         "seen": {"read": 0, "listen": 1}}
    conn.close()
