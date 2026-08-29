"""把精选汇编中的最高法指导性案例并入统一案例库（jsonl + index.csv，幂等去重）。

用法：
    python scripts/import_guiding_cases.py

输入：data/案例素材/最高法指导性案例-精选汇编.md（第一部分 30 个）
输出：data/案例库统一/documents/最高法指导性案例.jsonl 与 index.csv 追加/合并
后续：scripts/load_cases.py 装载进 cases 表。
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402

_CASE_HEAD = re.compile(r"^### 指导(?:性)?案例\s*(\d+)\s*号：(.*)$")
_FIELD = re.compile(r"^-\s*\*\*(关键词|裁判要点|裁判要旨|简要案情|裁判结果|法考意义)")
_DATE = re.compile(r"(\d{4}) 年 (\d{1,2}) 月 (\d{1,2}) 日发布")
_BATCH_INFO = re.compile(r"（.*）$")


def parse_guiding_cases(text: str) -> list[dict]:
    """解析精选汇编第一部分：指导性案例 N 号 段落 → 案例记录。"""
    records: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        m = _CASE_HEAD.match(line)
        if m:
            if current:
                records.append(current)
            num, rest = int(m.group(1)), m.group(2).strip()
            title = _BATCH_INFO.sub("", rest).strip()
            dm = _DATE.search(line)
            current = {
                "id": f"指导性案例{num:03d}号",
                "title": title,
                "category": "",
                "case_no": "",
                "keywords": [],
                "date": (f"{dm.group(1)}.{int(dm.group(2)):02d}."
                         f"{int(dm.group(3)):02d}") if dm else "",
                "url": "",
                "text_parts": [],
            }
            continue
        if current is None:
            continue
        fm = _FIELD.match(line)
        if fm:
            label = fm.group(1)
            value = line.split("：", 1)[1].strip() if "：" in line else ""
            if label == "关键词":
                current["keywords"] = [k.strip() for k in value.split("/") if k.strip()]
            else:
                current["text_parts"].append(f"{label}：{value}")
        elif current["text_parts"] and line.strip():
            current["text_parts"][-1] += line.strip()
    if current:
        records.append(current)
    for r in records:
        r["category"] = r["keywords"][0] if r["keywords"] else ""
        r["text"] = "\n".join(r["text_parts"])
        r.pop("text_parts")
    return records


def merge_records(existing: list[dict], new: list[dict]) -> list[dict]:
    """按 id 合并：新 id 追加；已存在的保留元数据，正文取更长者，关键词取并集。"""
    by_id = {r["id"]: r for r in existing}
    for rec in new:
        old = by_id.get(rec["id"])
        if old is None:
            by_id[rec["id"]] = rec
            continue
        if len(rec.get("text", "")) > len(old.get("text", "")):
            old["text"] = rec["text"]
        old["keywords"] = list(dict.fromkeys(
            [*(old.get("keywords") or []), *(rec.get("keywords") or [])]))
    return list(by_id.values())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="精选汇编指导性案例并入统一案例库")
    ap.add_argument("--md", default=str(config.DATA_DIR / "案例素材" / "最高法指导性案例-精选汇编.md"))
    ap.add_argument("--out", default=str(config.CASES_DIR))
    args = ap.parse_args(argv)

    md_text = Path(args.md).read_text(encoding="utf-8")
    new_records = parse_guiding_cases(md_text)
    jsonl_path = Path(args.out) / "documents" / "最高法指导性案例.jsonl"
    index_path = Path(args.out) / "index.csv"

    existing: list[dict] = []
    if jsonl_path.exists():
        existing = [json.loads(l) for l in
                    jsonl_path.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    merged = merge_records(existing, new_records)
    merged.sort(key=lambda r: r["id"])

    jsonl_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + "\n",
        encoding="utf-8")

    rows = []
    if index_path.exists():
        with index_path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    # 定位符在跨来源时可能重复（如 case_00001 各库都有），须以 (来源库, 定位符) 为键
    idx = {(r.get("来源库", ""), r.get("定位符", "")): r for r in rows if r.get("定位符")}
    for r in merged:
        idx[("最高法指导性案例", r["id"])] = {
            "定位符": r["id"], "来源库": "最高法指导性案例", "标题": r["title"],
            "类别": r["category"], "案号": r["case_no"],
            "关键词": " ".join(r["keywords"]), "日期": r["date"], "url": r["url"],
            "文档文件": "documents/最高法指导性案例.jsonl",
        }
    with index_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows
                                else list(idx.values())[0].keys())
        writer.writeheader()
        writer.writerows(idx.values())

    print(f"精选解析 {len(new_records)} 条，合并后共 {len(merged)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
