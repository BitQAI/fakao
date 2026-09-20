"""生成脚本共享工具测试：JSON 抽取、采分点清洗、材料清洗、写库、截断重试。"""
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import db  # noqa: E402
from scripts import subjective_build as sb  # noqa: E402


def test_extract_json_tolerates_fence_and_noise():
    assert sb.extract_json('好的：\n```json\n{"a": 1}\n```\n以上') == {"a": 1}


@pytest.mark.parametrize("bad", ["", "没有 json", "{不是合法}"])
def test_extract_json_returns_none(bad):
    assert sb.extract_json(bad) is None


def test_clean_points_rejects_bad_kind():
    clean, problems = sb.clean_points([{"kind": "感想", "text": "x"}], ("结论",))
    assert clean == [] and "kind 非法" in problems[0]


def test_clean_points_rejects_missing_text():
    clean, problems = sb.clean_points([{"kind": "结论", "text": " "}], ("结论",))
    assert clean == [] and "缺少 text" in problems[0]


def test_clean_points_requires_statute_for_cite_kinds():
    _, problems = sb.clean_points([{"kind": "依据", "text": "t"}], ("依据",))
    assert "没写法条依据" in problems[0]


def test_clean_points_essay_kinds_need_no_statute():
    clean, problems = sb.clean_points(
        [{"kind": "总论点", "text": "t"}], ("总论点",), must_cite=())
    assert problems == [] and clean[0]["kind"] == "总论点"


def test_clean_points_relax_marks_unverified():
    clean, problems = sb.clean_points(
        [{"kind": "依据", "text": "t", "statutes": ["不存在法第1条"]}],
        ("依据",), relax=True)
    assert problems == [] and clean[0]["verified"] is False


def test_clean_points_requires_qno_when_grouped():
    clean, problems = sb.clean_points(
        [{"kind": "结论", "text": "t"}], ("结论",), qno_max=3)
    assert clean == [] and "qno 非法" in problems[0]


def test_clean_points_rejects_qno_out_of_range():
    _, problems = sb.clean_points(
        [{"kind": "结论", "text": "t", "qno": 4}], ("结论",), qno_max=3)
    assert "qno 非法" in problems[0]


def test_clean_materials_relabels_by_order():
    mats, problems = sb.clean_materials([{"label": "甲", "text": "x" * 60}], 50, 100)
    assert problems == [] and mats[0]["label"] == "材料一"


def test_clean_materials_flags_out_of_range():
    mats, problems = sb.clean_materials([{"text": "太短"}], 50, 100)
    assert mats == [] and "长度" in problems[0]


def test_missing_kinds_reports_gaps():
    points = [{"kind": "总论点"}, {"kind": "实践措施"}]
    assert sb.missing_kinds(points, ("总论点", "材料结合", "实践措施")) == ["材料结合"]


def test_save_question_and_publish(tmp_db):
    conn = db.connect(tmp_db[0])
    qid = sb.save_question(
        conn, case_source="法治思想-核心论述", case_loc="essay-1", subject="理论法",
        qtype="essay", stem="s", questions=["q"],
        points=[{"no": 1, "kind": "总论点", "text": "t", "statutes": []}],
        reference="r", materials=[{"label": "材料一", "text": "材料"}])
    assert qid > 0
    assert sb.publish(conn, "essay") == 1
    row = conn.execute("SELECT qtype, materials, status FROM case_questions"
                       " WHERE id=?", (qid,)).fetchone()
    assert row["qtype"] == "essay" and row["status"] == "published"
    assert json.loads(row["materials"])[0]["label"] == "材料一"
    conn.close()


def test_save_question_ignores_duplicate(tmp_db):
    conn = db.connect(tmp_db[0])
    args = dict(case_source="s", case_loc="l", subject="民法", qtype="case",
                stem="x", questions=["q"], points=[], reference="")
    assert sb.save_question(conn, **args) > 0
    assert sb.save_question(conn, **args) == 0
    conn.close()


def test_llm_json_retries_with_bigger_budget(monkeypatch):
    """输出被截断（JSON 不可解析）时应加大额度重试一次。"""
    calls: list[int] = []

    def fake(system, user, temperature=0.3, max_tokens=1200):
        calls.append(max_tokens)
        return '{"a": 1}' if len(calls) > 1 else "被截断的{"

    monkeypatch.setattr(sb.ai, "call_llm", fake)
    assert sb.llm_json("s", "u", max_tokens=1000) == {"a": 1}
    assert calls == [1000, 2600]
