import wave

from app import config, db, tts, tts_audit


def _write_wav(path, seconds=3.0, rate=24000, amplitude=6000):
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = (amplitude).to_bytes(2, "little", signed=True) * int(rate * seconds)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


def test_audit_detects_missing_empty_and_fine(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    config.AUDIO_DIR.mkdir(parents=True)
    (config.AUDIO_DIR / "XF-002.wav").write_bytes(b"")
    _write_wav(config.AUDIO_DIR / "XF-003.wav", seconds=4.0)
    conn = db.connect(tmp_path / "a.db")
    rows = [{"id": "XF-001", "tts_text": "文本。"},
            {"id": "XF-002", "tts_text": "文本。"},
            {"id": "XF-003", "tts_text": "文" * 20 + "。"}]
    kinds = {i.entry_id: i.kind for i in
             tts_audit.audit_entries(conn, rows, wave_metrics=False)}
    assert kinds["XF-001"] == "missing"
    assert kinds["XF-002"] == "empty"
    # 20 字 / 4 秒 = 5 字每秒，落在正常区间 → 只有 untracked
    assert kinds["XF-003"] == "untracked"
    conn.close()


def test_audit_flags_truncated_audio(monkeypatch, tmp_path):
    """实测口径：>6.5 字/秒判定为截断（旧录音里 15 字/秒的那类）。"""
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    _write_wav(config.AUDIO_DIR / "SG-339.wav", seconds=2.0)
    conn = db.connect(tmp_path / "b.db")
    rows = [{"id": "SG-339", "tts_text": "撤销通知须在承诺发出前送达，否则撤销无效。"}]
    issues = tts_audit.audit_entries(conn, rows, wave_metrics=False)
    suspect = [i for i in issues if i.kind == "suspect"]
    assert len(suspect) == 1 and "语速异常" in suspect[0].detail
    assert suspect[0].chars_per_sec > tts_audit.MAX_RATE
    conn.close()


def test_audit_flags_stale_by_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    path = config.AUDIO_DIR / "XF-001.wav"
    _write_wav(path, seconds=6.0, amplitude=100)
    conn = db.connect(tmp_path / "c.db")
    old_text = "旧文本。" * 5
    tts.record_asset(conn, "XF-001", old_text, path)
    issues = tts_audit.audit_entries(
        conn, [{"id": "XF-001", "tts_text": "新文本，与旧的不同。" * 3}],
        wave_metrics=False)
    assert [i.kind for i in issues] == ["stale"]
    conn.close()


def test_audit_flags_silent_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    path = config.AUDIO_DIR / "XF-001.wav"
    _write_wav(path, seconds=6.0, amplitude=0)      # 全静音
    conn = db.connect(tmp_path / "d.db")
    tts.record_asset(conn, "XF-001", "文本。" * 5, path)
    issues = tts_audit.audit_entries(conn, [{"id": "XF-001", "tts_text": "文本。" * 5}])
    assert any("近乎无声" in i.detail for i in issues)
    conn.close()


def test_summarize_collects_repair_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    _write_wav(config.AUDIO_DIR / "XF-002.wav", seconds=0.5)
    conn = db.connect(tmp_path / "e.db")
    rows = [{"id": "XF-001", "tts_text": "文本。"},
            {"id": "XF-002", "tts_text": "很长的一段文本。" * 5}]
    summary = tts_audit.summarize(
        tts_audit.audit_entries(conn, rows, wave_metrics=False))
    assert summary["counts"]["missing"] == 1
    assert set(summary["repair_ids"]) == {"XF-001", "XF-002"}
    assert "XF-002" in summary["ids"]["suspect"]
    conn.close()


def test_wav_metrics_on_broken_file(monkeypatch, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav")
    assert tts_audit.wav_metrics(bad)["duration_sec"] == 0.0
    assert tts.audio_duration_sec(bad) == 0.0
