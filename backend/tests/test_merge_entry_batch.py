"""批次条目合并脚本测试。"""
import json

from scripts.merge_entry_batch import main, merge_file


def _entry(**kw):
    base = {"id": "XF-164", "subject": "刑法", "submodule": "总则-犯罪形态",
            "point": "犯罪中止", "anchor": "甲主动放弃犯罪并送被害人离开现场", "conclusion": "成立犯罪中止。",
            "priority": "高频考点", "rationale": "2026 真题", "sources": [],
            "statutes": [], "tts_text": "【刑法·犯罪中止】甲主动放弃犯罪。成立犯罪中止。"}
    base.update(kw)
    return base


def _target(tmp_path, entries=None, count=None):
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir(exist_ok=True)
    payload = {"schema": "fakao-entry/1.0", "status": "draft",
               "count": count if count is not None else len(entries or []),
               "entries": entries or []}
    (entries_dir / "刑法.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries_dir


def test_merge_appends_and_updates_count(tmp_path):
    entries_dir = _target(tmp_path, [_entry(id="XF-001", point="正当防卫")])
    stat = merge_file(entries_dir, "刑法", [_entry()], apply=True)
    assert stat["added"] == 1 and stat["before"] == 1 and stat["after"] == 2
    payload = json.loads((entries_dir / "刑法.json").read_text(encoding="utf-8"))
    assert payload["count"] == 2
    assert [e["id"] for e in payload["entries"]] == ["XF-001", "XF-164"]


def test_dry_run_keeps_file(tmp_path):
    entries_dir = _target(tmp_path, [_entry(id="XF-001", point="正当防卫")])
    stat = merge_file(entries_dir, "刑法", [_entry()], apply=False)
    assert stat["added"] == 1
    payload = json.loads((entries_dir / "刑法.json").read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 1


def test_duplicate_id_and_point_skipped(tmp_path):
    entries_dir = _target(tmp_path, [
        _entry(id="XF-164", point="犯罪中止"),
        _entry(id="XF-001", point="正当防卫"),
    ])
    stat = merge_file(entries_dir, "刑法",
                      [_entry(id="XF-164", point="犯罪中止"),
                       _entry(id="XF-165", point="正当防卫")], apply=True)
    assert stat["added"] == 0
    assert stat["dup_ids"] == ["XF-164"] and stat["dup_points"] == ["正当防卫"]


def test_unknown_subject_fails(tmp_path):
    entries_dir = _target(tmp_path)
    try:
        merge_file(entries_dir, "不存在科目", [_entry(subject="不存在科目")], apply=True)
    except FileNotFoundError as exc:
        assert "不存在科目" in str(exc)
    else:  # pragma: no cover - 明确失败
        raise AssertionError("应抛出 FileNotFoundError")


def test_cli_dry_run_then_apply(tmp_path, capsys):
    entries_dir = _target(tmp_path, [_entry(id="XF-001", point="正当防卫")])
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps(
        {"schema": "fakao-entry/1.0", "status": "draft", "count": 1,
         "entries": [_entry()]}, ensure_ascii=False), encoding="utf-8")

    assert main([str(batch), "--entries-dir", str(entries_dir)]) == 0
    assert "将写入 1 条" in capsys.readouterr().out
    assert main([str(batch), "--entries-dir", str(entries_dir), "--apply"]) == 0
    payload = json.loads((entries_dir / "刑法.json").read_text(encoding="utf-8"))
    assert payload["count"] == 2


def test_cli_bad_schema_fails(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "other/1.0", "entries": []}), encoding="utf-8")
    assert main([str(bad), "--entries-dir", str(tmp_path)]) == 1
