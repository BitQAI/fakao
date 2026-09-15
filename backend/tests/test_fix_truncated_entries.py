import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fix_truncated_entries import (  # noqa: E402
    check_repair,
    damage_reason,
    scan_damaged,
    statute_hints,
    unbalanced,
)


def entry(**kw):
    base = {"id": "SG-067", "point": "专属管辖范围",
            "anchor": "中外合资经营企业合同纠纷，能否协议选择外国法院管辖？",
            "conclusion": "由中国法院专属管辖（民诉法第279条）。",
            "statutes": ["民诉法第279条"], "sources": []}
    base.update(kw)
    return base


def test_damage_reason_detects_cut_citation_and_bracket():
    assert damage_reason(entry(conclusion="……不能协议排除（民诉法第2。"), "conclusion") is not None
    assert damage_reason(entry(conclusion="结论正常（民法典第157条）。"), "conclusion") is None
    assert damage_reason(entry(tts_text="文" * 150), "tts_text") is not None
    assert damage_reason(entry(anchor="短"), "anchor") is None


def test_scan_damaged_reports_field_and_reason():
    entries = [entry(), entry(id="MF-114", tts_text="【彩礼】(未闭合（依据民法典第5条")]
    hits = scan_damaged(entries)
    assert [(e["id"], f) for _, e, f, _ in hits] == [("MF-114", "tts_text")]


def test_unbalanced_pairs():
    assert unbalanced("（未闭合") is not None
    assert unbalanced("（已闭合）") is None


def test_check_repair_rejects_incomplete_citation():
    assert check_repair("conclusion", "旧（民诉法第2。", "新（民诉法第2。") is not None
    assert check_repair("conclusion", "旧。", "新（民诉法第279条）。") is None
    assert check_repair("tts_text", "旧", "新 `民诉法第279条`") is not None
    assert check_repair("conclusion", "这是一条足够长的旧结论。", "短。") is not None


def test_statute_hints_include_cited_article():
    hints = statute_hints(entry())
    assert hints, "应能从法条库取到条号候选"
    assert any(h["is_cited"] for h in hints)
