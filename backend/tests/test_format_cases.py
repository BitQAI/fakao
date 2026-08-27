import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from format_cases import main  # noqa: E402


def make_tree(tmp_path: Path) -> Path:
    src = tmp_path / "案例数据"
    (src / "人民法院案例库/cases").mkdir(parents=True)
    (src / "司法部案例库/cases").mkdir(parents=True)
    (src / "最高检指导性案例").mkdir(parents=True)
    (src / "最高法指导性案例").mkdir(parents=True)

    (src / "人民法院案例库/index.csv").write_text(
        "id,标题,分类,url,抓取时间\nabc,甲诉乙案,参考案例,http://x,2026-01-01\n",
        encoding="utf-8",
    )
    (src / "人民法院案例库/cases/case_00001.json").write_text(json.dumps({
        "id": "abc", "num": "00001", "title": "甲诉乙案", "type_name": "参考案例",
        "ajzh": "（2026）苏01民终1号", "keyword": ["民事", "合同"],
        "zs_date": "2026-01-01", "text": "<p>案情一</p>&nbsp;<br/>案情二",
    }, ensure_ascii=False), encoding="utf-8")

    (src / "司法部案例库/cases/case_00001.json").write_text(json.dumps({
        "title": "某调解案", "type": "人民调解案例", "num": "H001",
        "date": "2024-01-01", "url": "http://y", "body": "【案情简介】正文",
    }, ensure_ascii=False), encoding="utf-8")

    (src / "最高检指导性案例/index.csv").write_text(
        "批次,检例编号,标题,发布时间,来源URL\n"
        "第1批,检例第1号,甲案,2016-01-01,http://z\n"
        "第1批,检例第2号,乙案,2016-01-01,http://z\n",
        encoding="utf-8",
    )
    (src / "最高检指导性案例/第1批_检例1-2号.md").write_text(
        "# 第一批\n\n## 检例第1号　甲案\n\n【关键词】\n\n故意伤害 自首\n\n正文一\n\n"
        "## 检例第2号　乙案\n\n【关键词】\n\n盗窃\n\n正文二\n",
        encoding="utf-8",
    )

    (src / "最高法指导性案例/index.csv").write_text(
        "编号,标题,批次,日期,来源URL\n1,居间合同案,第1批,2012-01-01,http://c\n",
        encoding="utf-8",
    )
    (src / "最高法指导性案例/指导性案例001号.md").write_text(
        "# 指导性案例第1号：居间合同案\n\n关键词　民事　居间合同\n\n裁判要点\n\n要点正文\n",
        encoding="utf-8",
    )
    return src


def test_format_counts(tmp_path):
    src = make_tree(tmp_path)
    out = tmp_path / "案例库统一"
    assert main(["--data", str(src), "--out", str(out)]) == 0
    assert len(list(out.rglob("*.jsonl"))) == 4
    index_rows = (out / "index.csv").read_text(encoding="utf-8").splitlines()
    assert len(index_rows) == 6  # 表头 + 5 条


def test_fields_and_clean_text(tmp_path):
    src = make_tree(tmp_path)
    out = tmp_path / "案例库统一"
    main(["--data", str(src), "--out", str(out)])
    records = [
        json.loads(line)
        for line in (out / "documents/人民法院案例库.jsonl")
        .read_text(encoding="utf-8").splitlines()
    ]
    r = records[0]
    assert r["id"] == "case_00001" and r["source"] == "人民法院案例库"
    assert r["case_no"] == "（2026）苏01民终1号"
    assert r["keywords"] == ["民事", "合同"]
    assert "<p>" not in r["text"] and "案情一" in r["text"]


def test_jcy_split_by_guide(tmp_path):
    src = make_tree(tmp_path)
    out = tmp_path / "案例库统一"
    main(["--data", str(src), "--out", str(out)])
    records = [
        json.loads(line)
        for line in (out / "documents/最高检指导性案例.jsonl")
        .read_text(encoding="utf-8").splitlines()
    ]
    assert [r["id"] for r in records] == ["检例第1号", "检例第2号"]
    assert records[0]["keywords"] == ["故意伤害", "自首"]


def test_zgfy_fields(tmp_path):
    src = make_tree(tmp_path)
    out = tmp_path / "案例库统一"
    main(["--data", str(src), "--out", str(out)])
    records = [
        json.loads(line)
        for line in (out / "documents/最高法指导性案例.jsonl")
        .read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["id"] == "指导性案例001号"
    assert records[0]["title"] == "居间合同案"
    assert records[0]["keywords"] == ["民事", "居间合同"]
    assert records[0]["category"] == "第1批"


def test_bad_file_does_not_abort(tmp_path):
    src = make_tree(tmp_path)
    (src / "人民法院案例库/cases/case_00002.json").write_text("{broken", encoding="utf-8")
    out = tmp_path / "案例库统一"
    assert main(["--data", str(src), "--out", str(out)]) == 0
    assert (out / "index.csv").exists()


def test_derive_keywords_criminal():
    from format_cases import _derive_keywords
    kws = _derive_keywords("张某盗窃案", "被告人张某多次入户盗窃，到案后如实供述并退赃，系累犯。",
                           "人民法院案例库")
    assert kws[0] == "刑事"
    assert "盗窃罪" in kws
    assert "累犯" in kws


def test_derive_keywords_civil():
    from format_cases import _derive_keywords
    kws = _derive_keywords("李某诉王某房屋租赁合同纠纷案",
                           "双方因房屋租赁合同履行发生争议，诉至法院，经调解结案。",
                           "人民法院案例库")
    assert kws[0] == "民事"
    assert "房屋租赁合同纠纷" in kws
