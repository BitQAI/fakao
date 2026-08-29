from pathlib import Path

from scripts.import_guiding_cases import main, merge_records, parse_guiding_cases

FIXTURE = """# 测试
### 指导性案例 225 号：江某某正当防卫案（第 40 批，2024 年 5 月 30 日发布）

- **关键词**：刑事/正当防卫/未成年人
- **裁判要点**（原文）：1. 对于防卫行为的界分，应当坚持主客观相统一。
- **简要案情**：江某某被群殴后持刀反击。
- **裁判结果**：宣告无罪。
- **法考意义**：刑法第 20 条正当防卫。

### 指导案例 1 号：上海中原物业顾问有限公司诉陶德华居间合同纠纷案（第一批，2011 年 12 月 20 日发布）

- **关键词**：民事/居间合同/跳单违约
- **裁判要旨（概述）**：禁止"跳单"约定合法有效。
- **简要案情**：买方另行委托中介成交。
- **裁判结果**：驳回诉请。
- **法考意义**：民法典第 965 条。
"""


def test_parse_guiding_cases():
    recs = parse_guiding_cases(FIXTURE)
    assert len(recs) == 2
    assert recs[0]["id"] == "指导性案例225号"
    assert recs[0]["title"] == "江某某正当防卫案"
    assert recs[0]["date"] == "2024.05.30"
    assert recs[0]["category"] == "刑事"
    assert recs[0]["keywords"][:3] == ["刑事", "正当防卫", "未成年人"]
    assert "刑法第 20 条正当防卫" in recs[0]["text"]
    assert "裁判要点" in recs[0]["text"]
    assert recs[1]["id"] == "指导性案例001号"
    assert recs[1]["date"] == "2011.12.20"


def test_merge_records_dedup_and_enrich():
    old = [{"id": "指导性案例001号", "title": "旧标题", "keywords": ["民事"],
            "text": "短"}]
    new = [{"id": "指导性案例001号", "title": "新标题", "keywords": ["民事", "跳单"],
            "text": "更长的正文内容"}]
    merged = merge_records(old, new)
    assert len(merged) == 1
    assert merged[0]["title"] == "旧标题"  # 保留既有元数据
    assert merged[0]["text"] == "更长的正文内容"
    assert merged[0]["keywords"] == ["民事", "跳单"]


def test_main_writes_jsonl_and_index(tmp_path, monkeypatch):
    md = tmp_path / "cases.md"
    md.write_text(FIXTURE, encoding="utf-8")
    out = tmp_path / "out"
    (out / "documents").mkdir(parents=True)
    (out / "documents" / "最高法指导性案例.jsonl").write_text(
        '{"id": "指导性案例001号", "source": "最高法指导性案例", "title": "已有",'
        ' "category": "", "case_no": "", "keywords": ["民事"], "date": "", "url": "",'
        ' "text": "短"}\n', encoding="utf-8")
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["--md", str(md), "--out", str(out)]) == 0
    lines = (out / "documents" / "最高法指导性案例.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == 2  # 001 号去重合并 + 225 号新增
    assert any('"id": "指导性案例225号"' in l for l in lines)
    idx = (out / "index.csv").read_text(encoding="utf-8")
    assert "指导性案例225号" in idx
    assert "江某某正当防卫案" in idx


def test_main_preserves_duplicate_locs_across_sources(tmp_path, monkeypatch):
    """定位符跨来源重复时不得丢行（回归：曾按 loc 单键去重导致 index 掉 1000+ 行）。"""
    md = tmp_path / "cases.md"
    md.write_text("### 指导案例 1 号：上海中原物业顾问有限公司诉陶德华居间合同纠纷案（第一批，2011 年 12 月 20 日发布）\n\n"
                  "- **关键词**：民事/居间合同\n- **裁判要旨（概述）**：跳单违约。\n"
                  "- **简要案情**：另行委托中介。\n- **裁判结果**：驳回。\n"
                  "- **法考意义**：民法典第 965 条。\n", encoding="utf-8")
    out = tmp_path / "out"
    (out / "documents").mkdir(parents=True)
    (out / "documents" / "最高法指导性案例.jsonl").write_text(
        '{"id": "指导性案例001号", "source": "最高法指导性案例", "title": "a",'
        ' "category": "", "case_no": "", "keywords": [], "date": "", "url": "", "text": "x"}\n',
        encoding="utf-8")
    index = out / "index.csv"
    index.write_text(
        "定位符,来源库,标题,类别,案号,关键词,日期,url,文档文件\n"
        "case_00001,人民法院案例库,民事案,,,民事,,,documents/人民法院案例库.jsonl\n"
        "case_00001,司法部案例库,行政案,,,行政,,,documents/司法部案例库.jsonl\n",
        encoding="utf-8")
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["--md", str(md), "--out", str(out)]) == 0
    lines = index.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4  # 头 + 原 2 行（不同来源同 loc）+ 指导性案例001号
    assert sum("case_00001" in l for l in lines) == 2
