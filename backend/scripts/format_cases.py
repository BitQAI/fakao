"""案例库统一格式化：4 个来源 → index.csv + documents/*.jsonl。

用法：
    python scripts/format_cases.py [--data DIR] [--out DIR]

默认输入 data/案例数据，默认输出 data/案例库统一。
输出：
    index.csv                    元数据（提交入库）
    documents/<来源库>.jsonl     全文（.gitignore，可再生成）
幂等：重复运行覆盖输出；单文件解析失败记 stderr 不中断。
"""
import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import case_terms as _ct  # noqa: E402

CASE_SOURCES = ("人民法院案例库", "司法部案例库", "最高检指导性案例", "最高法指导性案例")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u3000]+")
_HEADING_RE = re.compile(r"^##\s*检例第(\d+)号\s*(.*)$", re.MULTILINE)
_BATCH_RE = re.compile(r"第(\d+)批")

_CRIME_TERMS = _ct.CRIME_TERMS
_CAUSE_TERMS = _ct.CAUSE_TERMS
_CONCEPT_TERMS = _ct.CONCEPT_TERMS
_PROC_TERMS = _ct.PROC_TERMS
_ADMIN_MARK = _ct.ADMIN_MARK
_EXEC_MARK = _ct.EXEC_MARK


def clean_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _TAG_RE.sub("\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_index(index_csv: Path) -> list[dict]:
    if not index_csv.exists():
        return []
    with index_csv.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _parse_rmfy(cases_dir: Path, index: list[dict]) -> list[dict]:
    url_map = {r.get("id", ""): r.get("url", "") for r in index}
    records = []
    for p in sorted(cases_dir.glob("case_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: {p} 解析失败: {exc}", file=sys.stderr)
            continue
        records.append({
            "id": p.stem, "source": "人民法院案例库",
            "title": d.get("title", ""), "category": d.get("type_name", ""),
            "case_no": d.get("ajzh", ""), "keywords": d.get("keyword") or [],
            "date": d.get("zs_date", ""), "url": url_map.get(d.get("id", ""), ""),
            "text": clean_text(d.get("text", "")),
        })
    return records


def _parse_sfb(cases_dir: Path, index: list[dict] | None = None) -> list[dict]:
    records = []
    for p in sorted(cases_dir.glob("case_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: {p} 解析失败: {exc}", file=sys.stderr)
            continue
        records.append({
            "id": p.stem, "source": "司法部案例库",
            "title": d.get("title", ""), "category": d.get("type", ""),
            "case_no": d.get("num", ""), "keywords": [],
            "date": d.get("date", ""), "url": d.get("url", ""),
            "text": clean_text(d.get("body", "")),
        })
    return records


def _section_keywords(text: str, section: str) -> list[str]:
    m = re.search(rf"【{section}】\s*(.+?)(?:\n\n|【|$)", text, re.S)
    if not m:
        return []
    return [t for t in _WS_RE.split(m.group(1).strip()) if t]


def _parse_jcy(batch_md: Path, index: list[dict]) -> list[dict]:
    batch = (_BATCH_RE.search(batch_md.name) or [None, ""])[1]
    meta = {r.get("检例编号", ""): r
            for r in index
            if (_BATCH_RE.search(r.get("批次", "") or "") or [None, ""])[1] == batch}
    blocks = _HEADING_RE.split(batch_md.read_text(encoding="utf-8-sig"))
    records = []
    for i in range(1, len(blocks), 3):
        loc = f"检例第{blocks[i].strip()}号"
        m = meta.get(loc, {})
        records.append({
            "id": loc, "source": "最高检指导性案例",
            "title": blocks[i + 1].strip() or "", "category": f"第{batch}批",
            "case_no": "", "keywords": _section_keywords(blocks[i + 2], "关键词"),
            "date": m.get("发布时间", ""), "url": m.get("来源URL", ""),
            "text": clean_text(blocks[i + 2]),
        })
    return records


def _parse_jcy_batches(dir_: Path, index: list[dict]) -> list[dict]:
    records = []
    for p in sorted(dir_.glob("第*批*.md")):
        records.extend(_parse_jcy(p, index))
    return records


def _parse_zgfy(md: Path, index: list[dict]) -> dict:
    num = int(re.search(r"(\d+)", md.stem).group(1))
    meta = next((r for r in index if str(r.get("编号", "")).strip() == str(num)), {})
    text = md.read_text(encoding="utf-8-sig")
    keywords = []
    for line in text.splitlines():
        if line.startswith("关键词"):
            keywords = [t for t in _WS_RE.split(line[len("关键词"):].strip()) if t]
            break
    batch = meta.get("批次", "")
    if batch and not batch.startswith("第"):
        batch = f"第{batch}批"
    return {
        "id": f"指导性案例{num:03d}号", "source": "最高法指导性案例",
        "title": meta.get("标题", "") or md.stem, "category": batch or f"第{meta.get('批次', '')}批",
        "case_no": "", "keywords": keywords,
        "date": meta.get("日期", ""), "url": meta.get("来源URL", ""),
        "text": clean_text(text),
    }


def _parse_zgfy_batches(dir_: Path, index: list[dict]) -> list[dict]:
    return [_parse_zgfy(p, index) for p in sorted(dir_.glob("指导性案例*.md"))]


def _derive_keywords(title: str, text: str, source: str) -> list[str]:
    """关键词为空时，按 标题 + 原文 推导：部门法标签 + 罪名/案由 + 高频概念/程序词。"""
    hay = f"{title}\n{text}"
    cands: list[str] = []

    def hit(term: str) -> bool:
        return term in hay

    # 罪名（标题优先，再按原文；司法部调解案例跳过，防合同条款误标）
    if source != "司法部案例库":
        for term, kw in sorted(_CRIME_TERMS, key=lambda x: -len(x[1])):
            if term in title and kw not in cands:
                cands.append(kw)
        for term, kw in sorted(_CRIME_TERMS, key=lambda x: -len(x[1])):
            if term in text and kw not in cands:
                cands.append(kw)

    # 案由（标题优先，再按原文）
    for term, kw in sorted(_CAUSE_TERMS, key=lambda x: -len(x[1])):
        if term in title and kw not in cands:
            cands.append(kw)
    for term, kw in sorted(_CAUSE_TERMS, key=lambda x: -len(x[1])):
        if term in text and kw not in cands:
            cands.append(kw)

    # 考点概念词（标题优先，再按原文）
    for term, kw in sorted(_CONCEPT_TERMS, key=lambda x: -len(x[1])):
        if term in title and kw not in cands:
            cands.append(kw)
    for term, kw in sorted(_CONCEPT_TERMS, key=lambda x: -len(x[1])):
        if term in text and kw not in cands:
            cands.append(kw)

    # 程序/量刑词（原文计数，取出现次数多者）
    proc = sorted(
        (t for t in _PROC_TERMS if t in text and t not in cands),
        key=lambda t: (-text.count(t), -len(t)),
    )
    cands.extend(proc)

    # 重叠去重（长词优先保留，子串关系只留长者）
    kws: list[str] = []
    for kw in sorted(cands, key=len, reverse=True):
        if not any(kw == k or kw in k or k in kw for k in kws):
            kws.append(kw)
    order = {k: i for i, k in enumerate(cands)}
    kws.sort(key=lambda k: order[k])

    # 部门法标签放最前
    tag = None
    if (source != "司法部案例库" and any(hit(t) for t, _ in _CRIME_TERMS)) or \
            "有期徒刑" in text or "判处" in text or "强制医疗" in hay:
        tag = "刑事"
    elif hit("国家赔偿"):
        tag = "国家赔偿"
    elif any(hit(m) for m in _EXEC_MARK):
        tag = "执行"
    elif any(hit(m) for m in _ADMIN_MARK) or hit("行政"):
        tag = "行政"
    elif any(hit(t) for t, _ in _CAUSE_TERMS) or "纠纷" in title or "民事" in text:
        tag = "民事"
    elif source == "司法部案例库":
        tag = "民事"
    if tag:
        kws.insert(0, tag)

    return kws[:6]


def main(argv=None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description="案例库统一格式化")
    ap.add_argument("--data", default=str(repo_root / "data/案例数据"))
    ap.add_argument("--out", default=str(repo_root / "data/案例库统一"))
    args = ap.parse_args(argv)

    src = Path(args.data)
    out = Path(args.out)
    docs = out / "documents"
    docs.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("人民法院案例库", _parse_rmfy, src / "人民法院案例库/cases",
         src / "人民法院案例库/index.csv"),
        ("司法部案例库", _parse_sfb, src / "司法部案例库/cases", None),
        ("最高检指导性案例", _parse_jcy_batches, src / "最高检指导性案例",
         src / "最高检指导性案例/index.csv"),
        ("最高法指导性案例", _parse_zgfy_batches, src / "最高法指导性案例",
         src / "最高法指导性案例/index.csv"),
    ]

    all_records = []
    for source, fn, data_path, index_path in jobs:
        index = _read_index(index_path) if index_path else []
        records = fn(data_path, index)
        for r in records:
            if not r["keywords"]:
                r["keywords"] = _derive_keywords(r["title"], r["text"], r["source"])
        print(f"OK: {source} {len(records)} 条")
        all_records.extend(records)

    with (out / "index.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["定位符", "来源库", "标题", "类别", "案号", "关键词",
                         "日期", "url", "文档文件"])
        for r in all_records:
            writer.writerow([
                r["id"], r["source"], r["title"], r["category"], r["case_no"],
                " ".join(r["keywords"]), r["date"], r["url"],
                f"documents/{r['source']}.jsonl",
            ])

    for source in CASE_SOURCES:
        recs = [r for r in all_records if r["source"] == source]
        with (docs / f"{source}.jsonl").open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"OK: 共 {len(all_records)} 条 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
