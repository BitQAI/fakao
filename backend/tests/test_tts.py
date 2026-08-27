from app import config
from app import tts


def test_dry_run_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    out = tts.ensure_mp3("XF-001", "文本", dry_run=True)
    assert out.name == "XF-001.mp3" and not out.exists()


def test_existing_file_skips_synth(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    config.AUDIO_DIR.mkdir(parents=True)
    (config.AUDIO_DIR / "XF-001.mp3").write_bytes(b"x")
    assert tts.ensure_mp3("XF-001", "文本") == config.AUDIO_DIR / "XF-001.mp3"


def test_synth_builds_command(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    recorded = []
    monkeypatch.setattr(
        tts.subprocess, "run",
        lambda cmd, check, capture_output: recorded.append(cmd),
    )
    out = tts.ensure_mp3("XF-001", "你好")
    assert recorded == [[tts._edge_tts_bin(), "--voice", tts.VOICE, "--text", "你好",
                         "--write-media", str(out)]]
    assert out.parent == config.AUDIO_DIR


def test_synth_uses_resolved_bin(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(tts, "_edge_tts_bin", lambda: "/venv/bin/edge-tts")
    recorded = []
    monkeypatch.setattr(
        tts.subprocess, "run",
        lambda cmd, check, capture_output: recorded.append(cmd),
    )
    tts.ensure_mp3("XF-001", "你好")
    assert recorded[0][0] == "/venv/bin/edge-tts"


def test_synth_failure_returns_path_without_raise(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")

    def boom(*a, **k):
        raise FileNotFoundError("edge-tts")

    monkeypatch.setattr(tts.subprocess, "run", boom)
    out = tts.ensure_mp3("XF-001", "你好")
    assert not out.exists()


def test_empty_file_is_not_cached_and_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    config.AUDIO_DIR.mkdir(parents=True)
    (config.AUDIO_DIR / "XF-001.mp3").write_bytes(b"")
    calls = {"n": 0}

    def fake_run(cmd, check, capture_output):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.CalledProcessError(1, cmd)
        (config.AUDIO_DIR / "XF-001.mp3").write_bytes(b"ok")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    first = tts.ensure_mp3("XF-001", "文本")
    assert not first.exists()  # 失败后空文件被删除，下次可重试
    out = tts.ensure_mp3("XF-001", "文本")
    assert out.exists() and out.stat().st_size > 0
    assert calls["n"] == 2


def test_batch(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    outs = tts.ensure_batch([("XF-001", "a"), ("XF-002", "b")], dry_run=True)
    assert [p.name for p in outs] == ["XF-001.mp3", "XF-002.mp3"]
