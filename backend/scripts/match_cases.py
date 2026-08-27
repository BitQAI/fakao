"""为 cases 为空的条目程序化补配案例：关键词检索（index.csv）+ 正文核验（documents jsonl）。

用法：
    python scripts/match_cases.py [--dry-run]

默认：
    条目  data/entries/*.json
    索引  data/案例库统一/index.csv
    正文  data/案例库统一/documents/<来源库>.jsonl
仅补 cases 为空的条目；每案最多 3 条案例、每案例全局最多引用 3 次；
--dry-run 只打印报告不写文件。标题由 importer 导入时自动补全。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import case_terms as ct  # noqa: E402

MIN_SCORE = 6
MIN_TEXT_HITS = 2
SPECIFIC_TERM_HIT = 1  # point 命中的考点专用词必须出现在正文
MAX_CASES_PER_ENTRY = 3
MAX_REFS_PER_CASE = 3

ALL_TERMS = [*ct.CRIME_TERMS, *ct.CAUSE_TERMS, *ct.CONCEPT_TERMS]


def entry_terms(e: dict) -> list[str]:
    """从条目提取考点词：specific=point 字段命中词，all=全字段命中词。"""
    point_text = " ".join([e.get("point", ""), e.get("submodule", "")])
    all_text = " ".join([point_text, e.get("anchor", ""), e.get("conclusion", "")])
    terms: list[str] = []
    specific: list[str] = []
    for term, kw in ALL_TERMS:
        if term in point_text and kw not in specific:
            specific.append(kw)
        if term in all_text:
            for t in (term, kw):
                if t not in terms:
                    terms.append(t)
    for t in ct.PROC_TERMS:
        if t in all_text and t not in terms:
            terms.append(t)
        if t in point_text and t not in specific:
            specific.append(t)
    return terms, specific


def score_case(terms: list[str], specific: list[str], title: str,
               keywords: str, text: str) -> tuple[int, int, int, int]:
    """返回 (总分, 正文命中数, 专用词正文命中数, 关键词+标题命中数)。"""
    kw_str = keywords or ""
    kw_hits = sum(1 for t in terms if t in kw_str)
    title_hits = sum(1 for t in terms if t in title)
    text_hits = sum(1 for t in terms if t in text)
    spec_hits = sum(1 for t in specific if t in text)
    return (kw_hits * 2 + title_hits * 2 + text_hits,
            text_hits, spec_hits, kw_hits + title_hits)


def load_index(path: Path) -> list[dict]:
    import csv
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_texts(docs_dir: Path) -> dict[tuple[str, str], str]:
    texts: dict[tuple[str, str], str] = {}
    for p in sorted(docs_dir.glob("*.jsonl")):
        source = p.stem
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            d = json.loads(line)
            texts[(d["source"], d["id"])] = d.get("text") or ""
    return texts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="条目 cases 程序化补配")
    ap.add_argument("--entries", default=str(Path(__file__).resolve().parents[2] / "data/entries"))
    ap.add_argument("--index", default=str(Path(__file__).resolve().parents[2] / "data/案例库统一/index.csv"))
    ap.add_argument("--docs", default=str(Path(__file__).resolve().parents[2] / "data/案例库统一/documents"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    index_rows = load_index(Path(args.index))
    texts = load_texts(Path(args.docs))
    files = sorted(Path(args.entries).glob("*.json"))

    # 全局引用计数：已有 cases + 本次新增
    usage: dict[tuple[str, str], int] = {}
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8-sig"))
        for e in payload.get("entries", []):
            for c in e.get("cases") or []:
                usage[(c["source"], c["loc"])] = usage.get((c["source"], c["loc"]), 0) + 1

    stats = {"filled": 0, "no_terms": 0, "no_match": 0, "added": 0}
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8-sig"))
        changed = False
        for e in payload.get("entries", []):
            if e.get("cases"):
                continue
            terms, specific = entry_terms(e)
            if not terms:
                stats["no_terms"] += 1
                continue
            # 第一轮：关键词/标题粗筛（不读正文）
            cands = []
            for r in index_rows:
                k = sum(1 for t in terms if t in (r.get("关键词") or ""))
                t = sum(1 for t2 in terms if t2 in r["标题"])
                if k + t >= 1:
                    cands.append((r["来源库"], r["定位符"], r["标题"], r.get("关键词") or "", k * 2 + t * 2))
            cands.sort(key=lambda x: (-x[4], x[1]))
            # 第二轮：正文核验
            matched = []
            for source, loc, title, keywords, pre in cands[:15]:
                body = texts.get((source, loc), "")
                score, text_hits, spec_hits, _ = score_case(
                    terms, specific, title, keywords, body)
                if score >= MIN_SCORE and text_hits >= MIN_TEXT_HITS \
                        and spec_hits >= SPECIFIC_TERM_HIT:
                    matched.append((score, spec_hits, text_hits, source, loc, title))
            matched.sort(key=lambda x: (-x[0], -x[1], -x[2], x[4]))
            picked = []
            for score, spec_hits, text_hits, source, loc, title in matched:
                if len(picked) >= MAX_CASES_PER_ENTRY:
                    break
                key = (source, loc)
                if usage.get(key, 0) >= MAX_REFS_PER_CASE:
                    continue
                picked.append({"source": source, "loc": loc})
                usage[key] = usage.get(key, 0) + 1
            if not picked:
                stats["no_match"] += 1
                print(f"NO-MATCH {e['id']} {e['point']} terms={terms[:5]}")
                continue
            e["cases"] = picked
            stats["filled"] += 1
            stats["added"] += len(picked)
            changed = True
            locs = [f"{p['source'][:2]}#{p['loc']}" for p in picked]
            print(f"FILL {e['id']} {e['point']} -> {locs}")
        if changed and not args.dry_run:
            f.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\nsummary:", stats, "(dry-run)" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
