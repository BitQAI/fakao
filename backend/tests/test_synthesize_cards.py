"""法条题卡音频：预热挑目标、全量分片与台账建档。"""
import io
import wave

from app import config, db, service, tts
from scripts import synthesize_cards as sc

CARD_COLS = ("id, subject, submodule, point, anchor, conclusion, priority,"
             " rationale, sources, cases, statutes, note, tts_text, status,"
             " kind, options, article_text")


def _wav_bytes(seconds=1.0, rate=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((6000).to_bytes(2, "little", signed=True) * int(rate * seconds))
    return buf.getvalue()


def _card(conn, entry_id="XF-Q000001", *, subject="刑法",
          tts_text="法条依据：刑法269条。题目：甲的行为如何定性？答案：抢劫罪。",
          kind="card", priority="普通"):
    conn.execute(
        f"INSERT INTO entries ({CARD_COLS}) VALUES"
        " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry_id, subject, "刑法", f"{entry_id} · 题", "情境", "抢劫罪。", priority,
         "解析", "[]", "[]", '["刑法269条"]', None, tts_text, "final",
         kind, "[]", ""),
    )
    conn.commit()
    return entry_id


def test_pick_targets_skips_existing_and_shards_by_stride():
    rows = [{"id": f"XF-Q{i:06d}", "tts_text": "文本。"} for i in range(1, 8)]
    have = {"XF-Q000001"}
    assert [i for i, _ in sc.pick_targets(rows, have)] == [
        f"XF-Q{i:06d}" for i in range(2, 8)]

    parts = [sc.pick_targets(rows, have, shard=(i, 3)) for i in (1, 2, 3)]
    ids = [i for part in parts for i, _ in part]
    assert len(ids) == len(set(ids))                     # 分片互不重叠
    assert sorted(ids) == [f"XF-Q{i:06d}" for i in range(2, 8)]   # 并集=全集


def test_pick_targets_follows_queue_order():
    rows = [{"id": "XF-Q000002", "tts_text": "b"}, {"id": "XF-Q000001", "tts_text": "a"}]
    todo = sc.pick_targets(rows, set(), queue_ids=["XF-Q000001", "XF-Q000002"])
    assert [i for i, _ in todo] == ["XF-Q000001", "XF-Q000002"]
    # 不在卡片集合里的 ID（正式条目）被忽略
    assert sc.pick_targets(rows, set(), queue_ids=["XF-101"]) == []


def test_listen_card_ids_orders_cards_after_entries(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    _card(conn, "XF-Q000002")
    _card(conn, "XF-Q000001")
    _card(conn, "MF-Q000003", subject="民法")
    _card(conn, "XF-101", kind="entry")          # 正式条目不该出现
    ids = service.listen_card_ids(conn, limit=10)
    # 同优先级同类型：科目顺序（刑法 先于 民法）→ id
    assert ids == ["XF-Q000001", "XF-Q000002", "MF-Q000003"]
    assert service.listen_card_ids(conn, limit=2) == ids[:2]
    assert service.listen_card_ids(conn, limit=10, exclude={"XF-Q000001"}) == ids[1:]
    conn.close()


def test_main_synthesizes_cards_and_records_assets(tmp_db, monkeypatch):
    db_path, tmp_path = tmp_db
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(tts, "render_audio", lambda text: _wav_bytes())
    conn = db.connect(db_path)
    for i in range(1, 4):
        _card(conn, f"XF-Q{i:06d}")
    conn.close()

    assert sc.main(["--all", "--workers", "2"]) == 0
    conn = db.connect(db_path)
    assets = conn.execute("SELECT entry_id, text_hash, duration_sec FROM tts_assets"
                          " ORDER BY entry_id").fetchall()
    assert [a["entry_id"] for a in assets] == [f"XF-Q{i:06d}" for i in range(1, 4)]
    assert all(a["text_hash"] == tts.text_hash(
        "法条依据：刑法269条。题目：甲的行为如何定性？答案：抢劫罪。")
        for a in assets)
    assert all(a["duration_sec"] > 0 for a in assets)
    conn.close()
    # 幂等：再跑一次没有待合成项
    assert sc.main(["--all"]) == 0
    assert len(list((tmp_path / "audio").glob("*.wav"))) == 3


def test_main_dry_run_and_failure_leave_no_file(tmp_db, monkeypatch, capsys):
    db_path, tmp_path = tmp_db
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    conn = db.connect(db_path)
    _card(conn, "XF-Q000001")
    conn.close()

    assert sc.main(["--all", "--dry-run"]) == 0
    assert not list((tmp_path / "audio").glob("*.wav"))
    assert "待合成 1 张" in capsys.readouterr().out

    monkeypatch.setattr(tts, "render_audio", lambda text: None)
    assert sc.main(["--all", "--retries", "0"]) == 1
    assert not list((tmp_path / "audio").glob("*.wav"))
    conn = db.connect(db_path)
    assert conn.execute("SELECT COUNT(*) c FROM tts_assets").fetchone()["c"] == 0
    conn.close()


def test_main_prewarm_queue_targets_head_of_listen_queue(tmp_db, monkeypatch):
    db_path, tmp_path = tmp_db
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(tts, "render_audio", lambda text: _wav_bytes())
    conn = db.connect(db_path)
    for i in range(1, 6):
        _card(conn, f"XF-Q{i:06d}")
    conn.close()

    assert sc.main(["--queue", "2", "--workers", "2"]) == 0
    assert sorted(p.stem for p in (tmp_path / "audio").glob("*.wav")) == [
        "XF-Q000001", "XF-Q000002"]
