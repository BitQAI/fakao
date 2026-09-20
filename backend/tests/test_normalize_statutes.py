"""法条原文归一脚本测试（纯函数，不写 data/法条库）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from normalize_statutes import build_header, normalize_text  # noqa: E402


def test_normalize_keeps_articles_and_headings():
    raw = """中华人民共和国示例法

目　　录

第一章　总　　则

第二章　合　　同

第一章　总　　则

第一条　为了示例，制定本法。

第二条　本法所称合同，是指协议。
本条第二款内容。

-- 3 --

第二章　合　　同

第十条　当事人订立合同，可以采用书面形式。
"""
    lines, problems = normalize_text(raw)
    assert problems == []
    assert lines[0] == "第一章　总　　则"
    assert lines[1] == "第一条　为了示例，制定本法。"
    assert "本条第二款内容。" in lines[2]
    assert lines[3] == "第二章　合　　同"
    assert lines[4].startswith("第十条　")
    assert all("-- 3 --" not in l for l in lines)


def test_arabic_article_number_converted_to_chinese():
    lines, problems = normalize_text("第1165条　行为人因过错侵害他人民事权益的。")
    assert problems == []
    assert lines[0].startswith("第一千一百六十五条　")


def test_sub_article_kept_and_allowed_same_number():
    lines, problems = normalize_text(
        "第二百八十七条　利用计算机实施犯罪的。\n"
        "第二百八十七条之一　非法利用信息网络。\n"
        "第二百八十七条之二　帮助信息网络犯罪活动。")
    assert problems == []
    assert [l.split("\u3000")[0] for l in lines] == [
        "第二百八十七条", "第二百八十七条之一", "第二百八十七条之二"]


def test_non_increasing_article_number_reported():
    _, problems = normalize_text("第十条　甲。\n第五条　乙。")
    assert any("未递增" in p for p in problems)


def test_header_uses_meta_when_available():
    head = build_header("中华人民共和国示例法", {
        "found": True, "bbbs": "abc123", "公布日期": "2026-01-01",
        "施行日期": "2026-06-01", "效力状态": 3, "制定机关": "全国人民代表大会常务委员会",
        "其他版本": [{"title": "旧版", "公布日期": "2000-01-01", "施行日期": "2001-01-01"}],
    })
    text = "\n".join(head)
    assert "施行日期：2026-06-01" in text
    assert "bbbs=abc123" in text
    assert "2000-01-01公布" in text


def test_header_without_meta_marks_manual():
    text = "\n".join(build_header("示例法", None))
    assert "人工投递" in text
