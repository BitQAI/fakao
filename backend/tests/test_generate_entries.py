import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app import ai, config, statutes  # noqa: E402
from generate_entries import (  # noqa: E402
    SUBJECT_PREFIX,
    entry_errors,
    fix_anchor,
    fix_conclusion,
    fix_loc,
    fix_rationale,
    fix_tts,
    generate,
    next_id,
    parse_entries,
    split_blocks,
)


def test_subject_prefixes():
    assert SUBJECT_PREFIX["刑诉"] == "XS"
    assert SUBJECT_PREFIX["商经知"] == "SJ"


def test_split_blocks_by_heading():
    text = ("# 标题\n\n## 一、总则\n\n### 考点1：A\n内容1内容1内容1内容1内容1内容1内容1内容1\n"
            "### 考点2：B\n内容2内容2内容2内容2内容2内容2内容2内容2\n"
            "## 【易错点1】C\n内容3内容3内容3内容3内容3内容3内容3内容3")
    blocks = split_blocks(text)
    assert len(blocks) == 3
    assert blocks[0].startswith("### 考点1")
    assert blocks[2].startswith("## 【易错点1】")


def test_parse_entries_ok():
    payload = '[{"point": "A", "anchor": "x"}]'
    assert parse_entries(payload) == [{"point": "A", "anchor": "x"}]


def test_parse_entries_code_fence_and_bad():
    assert parse_entries("```json\n[{\"point\": \"A\"}]\n```") == [{"point": "A"}]
    assert parse_entries("{broken") is None
    assert parse_entries("普通文本") is None


def test_entry_errors_loc_miss_and_statute(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path)
    (tmp_path / "资料.md").write_text("原文句子一。", encoding="utf-8")

    ok = {
        "id": "XS-001", "subject": "刑诉", "submodule": "基本原则",
        "point": "无罪推定", "anchor": "甲被检察院作存疑不起诉，问是否属确定有罪",
        "conclusion": "不起诉不是确定有罪，被不起诉人无罪。",
        "priority": "高频考点", "rationale": "高频",
        "sources": [{"type": "高频", "ref": "资料.md", "loc": "原文句子一"}],
        "statutes": ["刑法16条"], "tts_text": "【刑诉·无罪推定】甲被不起诉，无罪。",
    }
    assert entry_errors(ok) == []

    bad_loc = dict(ok, sources=[{"type": "高频", "ref": "资料.md", "loc": "原文不存在"}])
    assert any("来源摘录" in e for e in entry_errors(bad_loc))


def test_next_id():
    assert next_id([], "XS") == "XS-001"
    assert next_id(["XS-001", "XS-002"], "XS") == "XS-003"
    assert next_id(["MF-099"], "XS") == "XS-001"


def test_fix_loc_finds_exact_substring(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path)
    (tmp_path / "资料.md").write_text(
        "第一章 管辖。立案管辖与审判管辖不分，把侦查当审判，是常见错误。\n",
        encoding="utf-8",
    )
    fixed = fix_loc("资料.md", "立案管辖与审判管辖不分，把侦查当审判是常见错误")
    assert fixed is not None and "常见错误" in fixed
    assert fixed in "第一章 管辖。立案管辖与审判管辖不分，把侦查当审判，是常见错误。\n"


def test_fix_loc_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path)
    (tmp_path / "资料.md").write_text("原文。", encoding="utf-8")
    assert fix_loc("资料.md", "完全不存在的摘录") is None


def test_fix_anchor_truncates_long():
    long_a = "这是一个非常长的场景描述" * 6
    fixed = fix_anchor(long_a)
    assert len(fixed) <= 36
    assert fix_anchor("短场景。") == "短场景。"


def test_fix_rationale_fills_by_priority():
    assert fix_rationale("", "高频考点") == "高频考点，常考细节。"
    assert fix_rationale("易错陷阱") is not None
    assert fix_rationale("已有理由。") == "已有理由。"


def test_fix_conclusion_truncates_and_adds_period():
    long_c = "这是一个非常长的结论" * 10
    fixed = fix_conclusion(long_c)
    assert len(fixed) <= 60 and fixed.endswith("。")
    no_period = fix_conclusion("结论没有句号但是很短")
    assert no_period.endswith("。")
    ok = fix_conclusion("结论正常且以句号结尾。")
    assert ok == "结论正常且以句号结尾。"


def test_fix_tts_truncates():
    long_tts = "内容" * 80
    assert len(fix_tts(long_tts)) <= 150
    assert fix_tts("短文本") == "短文本"


def test_generate_writes_draft_file(monkeypatch, tmp_path):
    subject_dir = tmp_path / "科目资料" / "刑诉"
    subject_dir.mkdir(parents=True)
    (subject_dir / "刑诉-高频考点.md").write_text(
        "# 刑诉\n### 考点1：无罪推定\n原文句子一。甲被不起诉，无罪。\n",
        encoding="utf-8",
    )
    entry = {
        "subject": "刑诉", "submodule": "基本原则", "point": "无罪推定",
        "anchor": "甲被检察院作存疑不起诉，是否属确定有罪",
        "conclusion": "不起诉不是确定有罪，被不起诉人无罪。",
        "priority": "高频考点", "rationale": "高频",
        "sources": [{"type": "高频", "ref": "刑诉-高频考点.md", "loc": "原文句子一"}],
        "statutes": [], "note": None,
        "tts_text": "【刑诉·无罪推定】甲被不起诉，无罪。",
    }

    def fake_call_llm(system, user, **k):
        return json.dumps([{**entry, "id": "XS-001"}], ensure_ascii=False)

    monkeypatch.setattr(ai, "call_llm", fake_call_llm)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path)
    out = tmp_path / "刑诉.json"
    stats = generate("刑诉", out_path=out, batch=1)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "fakao-entry/1.0"
    assert data["status"] == "draft"
    assert data["count"] == 1
    assert data["entries"][0]["id"] == "XS-001"
    assert stats["ok"] == 1 and stats["fail"] == 0


def test_generate_retries_then_fails(monkeypatch, tmp_path):
    subject_dir = tmp_path / "科目资料" / "刑诉"
    subject_dir.mkdir(parents=True)
    (subject_dir / "刑诉-高频考点.md").write_text(
        "### 考点1：无罪推定\n原文句子一。内容足够长以通过分块过滤。\n", encoding="utf-8")
    monkeypatch.setattr(ai, "call_llm", lambda *a, **k: "垃圾输出")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path)
    out = tmp_path / "刑诉.json"
    stats = generate("刑诉", out_path=out, batch=1)
    assert stats["ok"] == 0 and stats["fail"] == 1
    assert not out.exists()
