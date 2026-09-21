"""LLM 供应商链：opencode 优先、空响应回落、推理预算抬升、无 key 不调用。"""
from types import SimpleNamespace

from app import ai, config

#: conftest 的 autouse fixture 会把 `ai.provider_chain` 换成空链（单测不联网），
#: 本模块要验证真实链路，因此先抓住原始函数再在用例里装回去。
_REAL_CHAIN = ai.provider_chain


class _FakeClient:
    """记录调用参数，并按预设结果返回（异常/空串/文本）。"""

    def __init__(self, result, calls: list):
        self._result = result
        self._calls = calls
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self._calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._result))])


def _install(monkeypatch, results: dict, calls: list) -> None:
    """两家供应商都可用，按 api_key 区分返回结果。"""
    monkeypatch.setattr(ai, "provider_chain", _REAL_CHAIN)
    monkeypatch.setattr(config, "OPENCODE_API_KEY", "k-open")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "k-deep")
    monkeypatch.setattr(config, "LLM_PROVIDER_ORDER", ["opencode", "deepseek"])
    monkeypatch.setattr(ai, "_client", lambda api_key, base_url: _FakeClient(
        results.get(api_key, "unexpected"), calls))


def test_prefers_opencode_with_session_header_and_reasoning_budget(monkeypatch):
    calls: list = []
    _install(monkeypatch, {"k-open": '{"stem":"题"}', "k-deep": "不该用到"}, calls)
    out = ai.call_llm("sys", "user", max_tokens=700)

    assert out == '{"stem":"题"}'
    assert len(calls) == 1                       # 第一家成功就不再打第二家
    assert calls[0]["max_tokens"] == config.OPENCODE_MIN_MAX_TOKENS
    assert calls[0]["extra_headers"] == {
        "x-opencode-session": config.OPENCODE_SESSION}
    assert ai.provider_status()["last_used"] == "opencode"


def test_empty_response_falls_back_to_deepseek(monkeypatch):
    calls: list = []
    _install(monkeypatch, {"k-open": "   ", "k-deep": "兜底文本"}, calls)
    out = ai.call_llm("sys", "user", max_tokens=700)

    assert out == "兜底文本"
    assert [c["max_tokens"] for c in calls] == [
        config.OPENCODE_MIN_MAX_TOKENS, 700]      # DeepSeek 不抬预算
    assert "extra_headers" not in calls[1]
    assert ai.provider_status()["last_used"] == "deepseek"


def test_exception_falls_back(monkeypatch):
    calls: list = []
    _install(monkeypatch, {"k-open": RuntimeError("400 MissingSessionID"),
                           "k-deep": "兜底文本"}, calls)
    assert ai.call_llm("sys", "user") == "兜底文本"
    assert len(calls) == 2


def test_provider_chain_skips_providers_without_key(monkeypatch):
    monkeypatch.setattr(ai, "provider_chain", _REAL_CHAIN)
    monkeypatch.setattr(config, "OPENCODE_API_KEY", "")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "k-deep")
    monkeypatch.setattr(config, "LLM_PROVIDER_ORDER", ["opencode", "deepseek"])
    assert [p.name for p in ai.provider_chain()] == ["deepseek"]

    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    assert ai.provider_chain() == []


def test_chat_target_uses_configured_provider(monkeypatch):
    monkeypatch.setattr(config, "LLM_CHAT_PROVIDER", "opencode")
    monkeypatch.setattr(config, "OPENCODE_API_KEY", "k-open")
    client, model, extra = ai.chat_target()
    assert client is not None and model == config.OPENCODE_MODEL
    assert extra["x-opencode-session"] == config.OPENCODE_SESSION

    monkeypatch.setattr(config, "LLM_CHAT_PROVIDER", "deepseek")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "k-deep")
    _, model, extra = ai.chat_target()
    assert model == config.DEEPSEEK_MODEL and extra == {}
