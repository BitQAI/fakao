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
    assert recorded == [["edge-tts", "--voice", tts.VOICE, "--text", "你好",
                         "--write-media", str(out)]]
    assert out.parent == config.AUDIO_DIR


def test_batch(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    outs = tts.ensure_batch([("XF-001", "a"), ("XF-002", "b")], dry_run=True)
    assert [p.name for p in outs] == ["XF-001.mp3", "XF-002.mp3"]
