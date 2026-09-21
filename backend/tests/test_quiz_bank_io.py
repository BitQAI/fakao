"""题库进版本库：导出 / 导入（往返、幂等、状态过滤、schema 校验）。"""
import json

import pytest

from app import db, importer, quiz_bank, quiz_bank_io


def _seed_entries(conn) -> None:
    """quizzes.entry_id 有外键约束，挂条目的题必须先把条目导进来。"""
    importer.import_payload(conn, {
        "schema": "fakao-entry/1.0", "status": "final", "generated_at": "x",
        "count": 2,
        "entries": [{
            "id": f"XF-{i:03d}", "subject": "刑法", "submodule": "总则",
            "point": f"考点{i}", "anchor": f"甲实施行为{i}，案件事实完整描述",
            "conclusion": f"成立结论{i}。", "priority": "高频考点", "rationale": "x",
            "sources": [{"type": "高频", "ref": "刑法-高频考点.md",
                         "loc": "犯盗窃、诈骗、抢夺罪，为窝藏赃物、抗拒抓捕而当场使用暴力"}],
            "statutes": [], "note": None, "tts_override": None, "tts_text": "文本。"}
            for i in (1, 2)]})


def _seed_quizzes(conn) -> None:
    _seed_entries(conn)
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-001",
        subject="刑法", point="追诉时效", stem="条目题：甲的行为如何定性？",
        options=["A. 甲", "B. 乙"], answer="A", analysis="解析一",
        basis="中华人民共和国刑法第八十七条", status="published")
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id=None,
        subject="刑法", stem="法条题：骗取出口退税如何定性？",
        options=["A. 甲", "B. 乙"], answer="A", analysis="解析二",
        basis="中华人民共和国刑法第二百零四条", status="published")
    quiz_bank.save_question(
        conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE, entry_id=None,
        subject="刑法", stem="法定最高刑不满五年的，追诉时效为五年。",
        answer="对", analysis="对。", basis="中华人民共和国刑法第八十七条",
        status="published")
    quiz_bank.save_question(
        conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK, entry_id="XF-002",
        subject="民法", stem="草稿题不该被导出", options=["A. 甲"], answer="A",
        analysis="x", status="draft")


def test_export_splits_by_origin_and_subject_and_skips_draft(tmp_db):
    db_path, tmp_path = tmp_db
    conn = db.connect(db_path)
    _seed_quizzes(conn)
    out = tmp_path / "out"
    result = quiz_bank_io.export(conn, out)
    conn.close()

    names = sorted(f["path"].name for f in result["files"])
    assert names == ["bank-刑法.json", "judge-刑法.json"]
    assert result["total"] == 3                      # draft 不导出
    payload = json.loads((out / "bank-刑法.json").read_text(encoding="utf-8"))
    assert payload["schema"] == quiz_bank_io.SCHEMA
    assert payload["origin"] == "bank" and payload["subject"] == "刑法"
    assert payload["count"] == len(payload["items"]) == 2
    # 排序稳定：entry_id 为空（法条题）在前，随后按 basis 排序
    assert [i["basis"] for i in payload["items"]] == [
        "中华人民共和国刑法第二百零四条", "中华人民共和国刑法第八十七条"]
    assert all("entry_id" not in i for i in json.loads(
        (out / "judge-刑法.json").read_text(encoding="utf-8"))["items"])


def test_dumps_puts_one_item_per_line():
    text = quiz_bank_io.dumps("bank", "刑法", [
        {"entry_id": "", "qtype": "choice", "point": "", "stem": "题干",
         "options": ["A. 甲"], "answer": "A", "analysis": "解析",
         "basis": "刑法第1条", "variant": ""}])
    item_lines = [ln for ln in text.splitlines() if ln.strip().startswith("{")
                  and "stem" in ln]
    assert len(item_lines) == 1
    assert json.loads(item_lines[0].rstrip(","))["stem"] == "题干"
    assert json.loads(text)["count"] == 1            # 仍是合法 JSON


def test_import_round_trip_restores_bank(tmp_db, tmp_path):
    db_path, _ = tmp_db
    src = db.connect(db_path)
    _seed_quizzes(src)
    out = tmp_path / "out"
    quiz_bank_io.export(src, out)
    src.close()

    fresh = db.connect(tmp_path / "fresh.db")
    # entries 是 quizzes.entry_id 的外键目标：新机器先导 entries，再导题库
    _seed_entries(fresh)
    total = 0
    for path in sorted(out.glob("*.json")):
        payload = quiz_bank_io.parse(path.read_text(encoding="utf-8"))
        stats = quiz_bank_io.import_payload(fresh, payload)
        total += stats["written"]
        assert stats["orphan"] == 0
    rows = fresh.execute(
        "SELECT origin, qtype, stem, answer, basis, status FROM quizzes"
        " ORDER BY origin, stem").fetchall()
    assert total == 3
    assert [(r["origin"], r["status"]) for r in rows] == [
        ("bank", "published"), ("bank", "published"), ("judge", "published")]
    assert {r["basis"] for r in rows} == {
        "中华人民共和国刑法第八十七条", "中华人民共和国刑法第二百零四条"}

    # 再导入一次：幂等，不新增行
    for path in sorted(out.glob("*.json")):
        payload = quiz_bank_io.parse(path.read_text(encoding="utf-8"))
        stats = quiz_bank_io.import_payload(fresh, payload)
        assert stats["written"] == 0
        assert stats["skipped"] == len(payload["items"])
        assert stats["orphan"] == 0
    assert fresh.execute("SELECT COUNT(*) c FROM quizzes").fetchone()["c"] == 3
    fresh.close()


def test_import_skips_questions_whose_entry_is_missing(tmp_db, tmp_path):
    """目标库还没导 entries 时，挂条目的题跳过并计数，不中断整批导入。"""
    db_path, _ = tmp_db
    src = db.connect(db_path)
    _seed_quizzes(src)
    out = tmp_path / "out"
    quiz_bank_io.export(src, out)
    src.close()

    empty = db.connect(tmp_path / "empty.db")
    payload = quiz_bank_io.parse((out / "bank-刑法.json").read_text(encoding="utf-8"))
    stats = quiz_bank_io.import_payload(empty, payload)
    assert stats == {"written": 1, "skipped": 0, "orphan": 1}
    empty.close()


def test_parse_rejects_foreign_schema(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "fakao-entry/1.0", "items": []}),
                    encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        quiz_bank_io.parse(path.read_text(encoding="utf-8"))
