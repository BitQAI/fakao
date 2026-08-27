import pytest

from app import ai


def fake_entry():
    return {"id": "XF-001", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": "转化型抢劫", "anchor": "甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤",
            "conclusion": "成立抢劫罪：犯盗窃诈骗抢夺后为抗拒抓捕当场施暴（刑法269条）。",
            "priority": "高频考点", "note": "陷阱：当场含追捕途中"}


def test_call_llm_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(ai, "get_client", lambda: None)
    assert ai.call_llm("sys", "user") is None


def test_adjust_plan_ratio_fallback(monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: "not a number")
    assert ai.adjust_plan_ratio({"days_left": 5}) == 0.35


def test_adjust_plan_ratio_clamped(monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: "9.9")
    assert ai.adjust_plan_ratio({}) == 0.6


def test_reports_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: None)
    stats = {"date": "2026-08-27", "done": 30, "quota": 30, "wrong": 3,
             "listen_min": 90, "weak": "合同编", "days_left": 17}
    assert "合同编" in ai.generate_evening_report(stats)
    assert "30" in ai.generate_daily_rationale(stats)


def test_generate_quiz_parse_failure_returns_none(monkeypatch):
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: "```json\n{broken\n```")
    assert ai.generate_quiz(fake_entry()) is None


def test_generate_quiz_ok(monkeypatch):
    payload = '{"stem": "问：结论是？", "options": ["A. 抢劫罪", "B. 盗窃罪"], "answer": "A"}'
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: payload)
    q = ai.generate_quiz(fake_entry())
    assert q["qtype"] == "choice" and q["answer"] == "A"


def test_cloze_quiz_shape():
    q = ai.cloze_quiz(fake_entry())
    assert q["qtype"] == "cloze" and q["options"] == []
    assert "____" in q["stem"]
    assert q["answer"] == fake_entry()["conclusion"]


@pytest.mark.asyncio
async def test_stream_answer_fallback_without_key(monkeypatch):
    monkeypatch.setattr(ai, "get_async_client", lambda: None)
    chunks = [c async for c in ai.stream_answer("问题", "上下文")]
    assert chunks and "未配置" in "".join(chunks)
