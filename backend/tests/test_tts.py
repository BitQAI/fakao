import subprocess

from app import config
from app import tts


class FakeResp:
    def __init__(self, data=None, content=b""):
        self._json = data
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, *a, **k):
        self.captured = {"payload": None, "headers": None}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def post(self, url, json=None, headers=None):
        self.captured["payload"] = json
        self.captured["headers"] = headers
        return FakeResp(data={"output": {"audio": {"url": "http://audio/x.wav"}}})

    def get(self, url, timeout=None):
        return FakeResp(content=b"WAVDATA")


def _patch_client(monkeypatch, client=None):
    client = client or FakeClient()
    monkeypatch.setattr(tts.httpx, "Client", lambda *a, **k: client)
    return client


def test_dry_run_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    out = tts.ensure_mp3("XF-001", "文本", dry_run=True)
    assert out.name == "XF-001.wav" and not out.exists()


def test_existing_file_skips_synth(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    config.AUDIO_DIR.mkdir(parents=True)
    (config.AUDIO_DIR / "XF-001.wav").write_bytes(b"x")
    assert tts.ensure_mp3("XF-001", "文本") == config.AUDIO_DIR / "XF-001.wav"


def test_synth_posts_to_dashscope_and_writes_url_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TTS_MODELS", ["m1", "m2"])
    monkeypatch.setattr(config, "TTS_SPEED", 1.0)
    client = _patch_client(monkeypatch)
    out = tts.ensure_mp3("XF-001", "你好")
    payload = client.captured["payload"]
    assert payload["model"] == config.TTS_MODELS[0]
    assert payload["input"]["text"] == "你好"
    assert payload["input"]["voice"] == config.TTS_VOICE
    assert client.captured["headers"]["Authorization"] == "Bearer sk-test"
    assert out.read_bytes() == b"WAVDATA"


def test_synth_writes_base64_audio(monkeypatch, tmp_path):
    import base64

    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TTS_SPEED", 1.0)

    class B64Client(FakeClient):
        def post(self, url, json=None, headers=None):
            return FakeResp(data={"output": {"audio": {"data": base64.b64encode(b"B64WAV").decode()}}})

    _patch_client(monkeypatch, B64Client())
    out = tts.ensure_mp3("XF-001", "你好")
    assert out.read_bytes() == b"B64WAV"


def test_synth_without_key_does_not_call_api(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "")
    client = _patch_client(monkeypatch)
    out = tts.ensure_mp3("XF-001", "你好")
    assert not out.exists()
    assert client.captured["payload"] is None


def test_synth_failure_removes_file_and_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TTS_MODELS", ["m1"])
    calls = {"n": 0}

    class FailOnceClient(FakeClient):
        def post(self, url, json=None, headers=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("网络错误")
            return FakeResp(data={"output": {"audio": {"url": "http://audio/x.wav"}}})

    _patch_client(monkeypatch, FailOnceClient())
    first = tts.ensure_mp3("XF-001", "你好")
    assert not first.exists()  # 失败后不留空文件，下次可重试
    out = tts.ensure_mp3("XF-001", "你好")
    assert out.exists() and out.stat().st_size > 0
    assert calls["n"] == 2


def test_synth_falls_back_to_next_model(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TTS_MODELS", ["m1", "m2"])
    monkeypatch.setattr(config, "TTS_SPEED", 1.0)
    used = []

    class FallbackClient(FakeClient):
        def post(self, url, json=None, headers=None):
            used.append(json["model"])
            if json["model"] == "m1":
                raise RuntimeError("模型 m1 不可用")
            return FakeResp(data={"output": {"audio": {"url": "http://audio/x.wav"}}})

    _patch_client(monkeypatch, FallbackClient())
    out = tts.ensure_mp3("XF-001", "你好")
    assert used == ["m1", "m2"]
    assert out.exists() and out.read_bytes() == b"WAVDATA"


def test_synth_all_models_fail_leaves_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TTS_MODELS", ["m1", "m2"])
    used = []

    class AllFailClient(FakeClient):
        def post(self, url, json=None, headers=None):
            used.append(json["model"])
            raise RuntimeError("不可用")

    _patch_client(monkeypatch, AllFailClient())
    out = tts.ensure_mp3("XF-001", "你好")
    assert used == ["m1", "m2"]
    assert not out.exists()


def test_batch(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    outs = tts.ensure_batch([("XF-001", "a"), ("XF-002", "b")], dry_run=True)
    assert [p.name for p in outs] == ["XF-001.wav", "XF-002.wav"]


def test_slow_down_speed_one_returns_unchanged(monkeypatch):
    monkeypatch.setattr(config, "TTS_SPEED", 1.0)
    assert tts._slow_down(b"RAW") == b"RAW"


def test_slow_down_runs_ffmpeg_atempo(monkeypatch):
    monkeypatch.setattr(config, "TTS_SPEED", 0.9)
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=b"SLOWED")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    assert tts._slow_down(b"RAW") == b"SLOWED"
    assert captured["args"][:2] == ["ffmpeg", "-y"]
    assert "atempo=0.900000" in captured["args"]


def test_slow_down_falls_back_when_ffmpeg_fails(monkeypatch):
    monkeypatch.setattr(config, "TTS_SPEED", 0.9)

    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["ffmpeg"])

    monkeypatch.setattr(tts.subprocess, "run", boom)
    assert tts._slow_down(b"RAW") == b"RAW"


def test_ensure_mp3_applies_slow_down(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(config, "DASHSCOPE_API_KEY", "sk-test")
    monkeypatch.setattr(config, "TTS_MODELS", ["m1"])
    monkeypatch.setattr(config, "TTS_SPEED", 0.9)
    _patch_client(monkeypatch)

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=b"SLOWED")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    out = tts.ensure_mp3("XF-001", "你好")
    assert out.read_bytes() == b"SLOWED"
