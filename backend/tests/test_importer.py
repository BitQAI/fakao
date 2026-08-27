import json

import pytest

from app import db
from app import importer


def make_sidecar(entries, status="final"):
    return {"schema": "fakao-entry/1.0", "source_md": "03_条目库/刑法.md",
            "status": status, "generated_at": "2026-08-27T00:00:00",
            "count": len(entries), "entries": entries}


def good_entry(i=1):
    return {"id": f"XF-{i:03d}", "subject": "刑法", "submodule": "分则-财产犯罪",
            "point": "转化型抢劫", "anchor": "甲盗窃后被失主当场扭住，为挣脱反抗将失主打成轻伤",
            "conclusion": "成立抢劫罪。", "priority": "★", "tags": ["对比"],
            "rationale": "历年高频", "sources": [{"type": "高频", "ref": "刑法-高频考点.md", "loc": "二.10"}],
            "statutes": ["刑法269条"], "note": "陷阱：当场含追捕途中", "tts_override": None,
            "tts_text": "【刑法·转化型抢劫】甲盗窃后……成立抢劫罪。"}


def test_schema_mismatch_rejected(tmp_db, tmp_path):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"schema": "other/9.9", "entries": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        importer.load_payload(p)


def test_import_ok(tmp_db, tmp_path, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    monkeypatch.setattr(importer.config, "SOURCE_DIR", tmp_path)
    (tmp_path / "刑法-高频考点.md").write_text("x", encoding="utf-8")
    importer._REF_CACHE.clear()
    payload = make_sidecar([good_entry()])
    result = importer.import_payload(conn, payload)
    assert result == {"imported": 1, "errors": [], "warnings": []}
    row = conn.execute("SELECT id, status FROM entries WHERE id='XF-001'").fetchone()
    assert row["id"] == "XF-001" and row["status"] == "final"


def test_import_rejects_whole_batch_on_error(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    bad = good_entry()
    bad["priority"] = "??"
    result = importer.import_payload(conn, make_sidecar([good_entry(), bad]))
    assert result["imported"] == 0 and result["errors"]
    assert conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"] == 0


def test_validate_anchor_length():
    e = good_entry()
    e["anchor"] = "太短"
    assert any("锚点句" in msg for msg in importer.validate_entry(e, 0))


def test_validate_bad_id():
    e = good_entry()
    e["id"] = "XX-1"
    assert any("ID" in msg for msg in importer.validate_entry(e, 0))


def test_validate_bad_tags():
    e = good_entry()
    e["tags"] = ["不存在"]
    assert any("标签" in msg for msg in importer.validate_entry(e, 0))


def test_ref_missing_warns(tmp_db, tmp_path, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    monkeypatch.setattr(importer.config, "SOURCE_DIR", tmp_path)
    importer._REF_CACHE.clear()
    result = importer.import_payload(conn, make_sidecar([good_entry()]))
    assert result["imported"] == 1
    assert any("来源文件不存在" in w for w in result["warnings"])


def _write_case_index(tmp_path, rows):
    p = tmp_path / "index.csv"
    p.write_text("定位符,来源库,标题\n" + "".join(rows), encoding="utf-8")
    return p


def test_cases_valid_ok(tmp_db, tmp_path, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    monkeypatch.setattr(importer.config, "CASES_INDEX",
                        _write_case_index(tmp_path, ["case_00001,人民法院案例库,甲案\n"]))
    importer._CASE_LOC_CACHE.clear()
    e = good_entry()
    e["cases"] = [{"source": "人民法院案例库", "loc": "case_00001"}]
    result = importer.import_payload(conn, make_sidecar([e]))
    assert result["imported"] == 1 and result["errors"] == []


def test_cases_missing_loc_error(tmp_db, tmp_path, monkeypatch):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    monkeypatch.setattr(importer.config, "CASES_INDEX",
                        _write_case_index(tmp_path, []))
    importer._CASE_LOC_CACHE.clear()
    e = good_entry()
    e["cases"] = [{"source": "人民法院案例库", "loc": "case_99999"}]
    result = importer.import_payload(conn, make_sidecar([e]))
    assert result["imported"] == 0
    assert any("案例" in msg and "不存在" in msg for msg in result["errors"])


def test_cases_bad_shape_error(tmp_db):
    db_path, _ = tmp_db
    conn = db.connect(db_path)
    e = good_entry()
    e["cases"] = [{"source": "不存在的库", "loc": "x"}, {"source": "人民法院案例库", "loc": "y", "extra": 1}]
    errors = importer.validate_entry(e, 0)
    assert any("案例" in msg for msg in errors)
