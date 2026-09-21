"""法条题卡条目化：ID 规则、字段映射、幂等、文本漂移、下架处理。"""
from app import card_entries, config, db, quiz_bank, service, statute_index, statutes

LAW = """# 中华人民共和国刑法

第一条　为了惩罚犯罪，保护人民，根据宪法，制定本法。
第二条　中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争。
第三条　法律明文规定为犯罪行为的，依照法律定罪处刑。
"""


def _prepare(tmp_path, monkeypatch):
    law_dir = tmp_path / "法条库"
    law_dir.mkdir()
    (law_dir / "中华人民共和国刑法.md").write_text(LAW, encoding="utf-8")
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    monkeypatch.setattr(config, "STATUTE_DIR", law_dir)
    monkeypatch.setattr(config, "AUDIO_DIR", audio_dir)
    statute_index.clear_cache()
    statutes._LAW_FILE_CACHE.clear()
    return audio_dir


def _seed(conn, n: int = 3) -> list[int]:
    ids = []
    for i in range(n):
        ids.append(quiz_bank.save_question(
            conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
            subject="刑法", stem=f"法条题{i}：甲的行为应如何定性？",
            options=["A. 甲", "B. 乙"], answer="A", analysis=f"解析{i}",
            basis=f"中华人民共和国刑法第{statute_index.int2cn(i + 1)}条",
            status="published"))
    return ids


def test_entry_id_rules():
    assert card_entries.entry_id_for("刑法", 162) == "XF-Q000162"
    assert card_entries.entry_id_for("商经知劳环", 8) == "SJ-Q000008"
    assert card_entries.entry_id_for("未知科目", 1) == "QT-Q000001"
    assert card_entries.quiz_id_of("XF-Q000162") == 162
    assert card_entries.quiz_id_of("XF-001") is None
    assert card_entries.quiz_id_of("XF-Q00x") is None


def test_sync_creates_cards_with_mapped_fields(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    ids = _seed(conn)

    counts = card_entries.sync(conn)
    assert counts["created"] == 3 and counts["total"] == 3

    row = conn.execute("SELECT * FROM entries WHERE id=?",
                       (card_entries.entry_id_for("刑法", ids[0]),)).fetchone()
    assert row["kind"] == "card"
    assert row["subject"] == "刑法"
    assert row["submodule"] == "中华人民共和国刑法"
    assert row["point"].startswith("刑法第一条 · ")
    assert row["anchor"] == "法条题0：甲的行为应如何定性？"
    assert row["conclusion"] == "A"
    assert row["rationale"] == "解析0"
    assert row["priority"] == "普通"
    assert row["status"] == "final"
    assert '"中华人民共和国刑法第一条"' in row["statutes"].replace(" ", "")
    assert row["options"] == '["A. 甲", "B. 乙"]'
    assert row["article_text"].startswith("为了惩罚犯罪，保护人民")
    assert "法条依据：中华人民共和国刑法第一条" in row["tts_text"]
    # 卡片不进条目空间
    assert conn.execute("SELECT COUNT(*) FROM v_entries").fetchone()[0] == 0
    # 卡片进听学池
    items, _ = service._listen_pool(conn)
    assert len(items) == 3


def test_sync_is_idempotent(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    _seed(conn)
    card_entries.sync(conn)
    again = card_entries.sync(conn)
    assert again["created"] == 0 and again["updated"] == 0
    assert again["unchanged"] == 3


def test_sync_updates_text_and_drops_stale_audio(tmp_db, tmp_path, monkeypatch):
    audio_dir = _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    quiz_id = _seed(conn, 1)[0]
    card_entries.sync(conn)
    card_id = card_entries.entry_id_for("刑法", quiz_id)

    wav = audio_dir / f"{card_id}.wav"
    wav.write_bytes(b"RIFF0000")
    conn.execute("INSERT INTO tts_assets (entry_id, text_hash, speed, bytes,"
                 " duration_sec, created_at) VALUES (?,?,?,?,?,?)",
                 (card_id, "old", 1.0, 8, 1.0, "2026-09-20T10:00:00"))
    conn.commit()

    conn.execute("UPDATE quizzes SET stem=? WHERE id=?",
                 ("法条题0：改写后的题干？", quiz_id))
    conn.commit()
    counts = card_entries.sync(conn)
    assert counts["updated"] == 1
    row = conn.execute("SELECT * FROM entries WHERE id=?", (card_id,)).fetchone()
    assert "改写后的题干" in row["anchor"] and "改写后的题干" in row["tts_text"]
    # 朗读文本变了：旧音频与台账作废，听学时按需重合成
    assert not wav.exists()
    assert conn.execute("SELECT COUNT(*) FROM tts_assets WHERE entry_id=?",
                        (card_id,)).fetchone()[0] == 0


def test_sync_archives_card_when_question_unpublished(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    quiz_id = _seed(conn, 1)[0]
    card_entries.sync(conn)
    card_id = card_entries.entry_id_for("刑法", quiz_id)

    conn.execute("UPDATE quizzes SET status='archived' WHERE id=?", (quiz_id,))
    conn.commit()
    counts = card_entries.sync(conn)
    assert counts["cleaned"] == 1
    row = conn.execute("SELECT status FROM entries WHERE id=?", (card_id,)).fetchone()
    assert row["status"] == "draft"
    items, _ = service._listen_pool(conn)
    assert items == []


def test_judge_questions_never_become_cards(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    _seed(conn, 1)
    judge_id = quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, entry_id=None,
        subject="刑法", stem="刑法第一条是关于立法目的的规定。", options=[],
        answer="对", analysis="依据原文。", basis="中华人民共和国刑法第一条",
        status="published")

    counts = card_entries.sync(conn)
    assert counts["total"] == 1                      # 判断题不进卡片池
    cards = {r["id"] for r in conn.execute("SELECT id FROM entries WHERE kind='card'")}
    assert card_entries.entry_id_for("刑法", judge_id) not in cards

    # 已经存在的判断题卡片（历史遗留）被清理删除
    card_entries.upsert(conn, conn.execute(
        "SELECT id, subject, qtype, stem, options, answer, analysis, basis"
        " FROM quizzes WHERE id=?", (judge_id,)).fetchone())
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM entries WHERE kind='card'"
                        ).fetchone()[0] == 2
    counts = card_entries.sync(conn)
    assert counts["cleaned"] == 1
    assert conn.execute("SELECT COUNT(*) FROM entries WHERE kind='card'"
                        ).fetchone()[0] == 1


def test_dry_run_writes_nothing(tmp_db, tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    conn = db.connect(tmp_db[0])
    _seed(conn)
    counts = card_entries.sync(conn, dry_run=True)
    assert counts["created"] == 3
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
