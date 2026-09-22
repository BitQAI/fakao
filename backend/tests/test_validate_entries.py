"""导入前干跑校验脚本测试。"""
import json

from scripts.validate_entries import main


def _write(tmp_path, entries, schema="fakao-entry/1.0"):
    path = tmp_path / "batch.json"
    path.write_text(json.dumps({
        "schema": schema, "status": "draft", "count": len(entries), "entries": entries,
    }, ensure_ascii=False), encoding="utf-8")
    return path


def _entry():
    return {"id": "XF-701", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": "转化型抢劫", "anchor": "甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤",
            "conclusion": "成立抢劫罪（刑法第269条）。", "priority": "高频考点",
            "rationale": "2026 真题", "sources": [{"type": "真题", "ref": "不存在.md",
                                                 "loc": "0912-卷二-T018"}],
            "statutes": [], "tts_text": "【刑法·转化型抢劫】甲盗窃后被失主当场扭住，成立抢劫罪。"}


def test_clean_batch_passes(tmp_path, capsys):
    assert main([str(_write(tmp_path, [_entry()]))]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out and "1 条通过" in out
    assert "W:" in out  # 来源文件不存在 → 软警告，不拦


def test_bad_id_fails(tmp_path, capsys):
    bad = _entry()
    bad["id"] = "XF-2026-018"
    assert main([str(_write(tmp_path, [bad]))]) == 1
    assert "E:" in capsys.readouterr().out


def test_missing_field_fails(tmp_path):
    broken = _entry()
    broken.pop("conclusion")
    assert main([str(_write(tmp_path, [broken]))]) == 1


def test_schema_mismatch_fails(tmp_path):
    path = _write(tmp_path, [_entry()], schema="fakao-entry/9.9")
    assert main([str(path)]) == 1


def test_no_args_returns_usage():
    assert main([]) == 2
