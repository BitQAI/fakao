"""全库法条引用核查（只读，不写任何数据）。

用法：
    python scripts/audit_statute_citations.py              # 打印四类结论
    python scripts/audit_statute_citations.py --json out.json

六类：
  A 条号不存在 —— 法名命中法条库，但条号在库内查不到（硬错误）
  B 库外法     —— 引用的法律/公约/意见不在 data/法条库，无法校验（覆盖缺口）
  C 命名不统一 —— 同一部法出现多种写法
  D 语义存疑   —— 现引条文与该条目 point 零字面重合，而其他条文有强候选（需人工判定）
  E 正文内嵌   —— conclusion/note/tts_text 里出现未登记在 statutes 的条号
  F 未带条号   —— statutes 只写了法名，没有条号

D 类只做定位，不判定对错：结论被 LLM 改写后可能与正确条文同样不重合。
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import config, statutes  # noqa: E402
from app.statutes import _cn2int  # noqa: E402  复用条号归一（含中文数字）
from fix_truncated_entries import _article_blocks, _grams, _law_of  # noqa: E402

TEXT_FIELDS = ("conclusion", "note", "tts_text")
INLINE_REF = re.compile(
    r"(?:依据|根据|按照|参照|依|按)?《?([\u4e00-\u9fa5A-Za-z]{2,20}?)》?"
    r"第([\d零一二三四五六七八九十百千]+)条")
NUM_RE = re.compile(r"第?([\d零一二三四五六七八九十百千]+)条")

# 法条库已收录、但 app.STATUTE_ALIASES 尚未登记的写法（建议 app 侧同步）
AUDIT_ALIASES = {
    "民诉解释": "最高人民法院关于适用《中华人民共和国民事诉讼法》的解释",
    "民诉法解释": "最高人民法院关于适用《中华人民共和国民事诉讼法》的解释",
    "刑诉法解释": "最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释",
    "证据规定": "最高人民法院关于民事诉讼证据的若干规定",
    "民事证据规定": "最高人民法院关于民事诉讼证据的若干规定",
}


def load_entries(root: Path) -> list[dict]:
    out = []
    for path in sorted((root / "data/entries").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.extend(data["entries"] if isinstance(data, dict) else data)
    return out


def coverage(text: str, body: str) -> float:
    """text 的 4-gram 有多少比例出现在 body 中。"""
    grams = _grams(text or "")
    if not grams:
        return 0.0
    return len(grams & _grams(body or "")) / len(grams)


def resolve_path(law: str) -> Path | None:
    """法名 → 法条库文件；app 别名优先，其次审计补充别名。"""
    path = statutes.resolve_law_file(law)
    if path is None and law in AUDIT_ALIASES:
        candidate = config.STATUTE_DIR / f"{AUDIT_ALIASES[law]}.md"
        path = candidate if candidate.exists() else None
    return path


def best_alternative(point: str, blocks: dict[str, str], cited_num: str) -> tuple[str, float]:
    """与 point 重合度最高的非现引条文 → (条号, 重合度)。"""
    best = ("", 0.0)
    for num, body in blocks.items():
        if num == cited_num:
            continue
        score = coverage(point, body)
        if score > best[1]:
            best = (num, round(score, 2))
    return best


def audit_entry(e: dict, result: dict) -> None:
    point = e.get("point") or ""
    for st in e.get("statutes") or []:
        law = _law_of(st)
        path = resolve_path(law)
        if path is None:
            result["b_unknown"][law] += 1
            result["b_rows"].append({"id": e["id"], "ref": st})
            continue
        result["c_writings"][path.name].add(law)
        m = NUM_RE.search(st)
        if not m:
            result["f_no_number"].append(
                {"id": e["id"], "subject": e.get("subject"), "ref": st})
            continue
        blocks = {num: body for num, body in
                  ((_cn2int(k), v) for k, v in _article_blocks(path).items())
                  if num is not None}
        cited_num = _cn2int(m.group(1))
        cited = blocks.get(cited_num)
        if cited is None:
            result["a_missing"].append(
                {"id": e["id"], "subject": e.get("subject"), "ref": st})
            continue
        alt, alt_score = best_alternative(point, blocks, cited_num)
        row = {
            "id": e["id"], "subject": e.get("subject"), "point": point, "ref": st,
            "cited_cov": round(coverage(point, cited), 2),
            "alt": f"{law}第{alt}条" if alt else "",
            "alt_cov": alt_score,
        }
        if row["cited_cov"] == 0.0 and alt_score >= 0.5:
            result["d_high"].append(row)
        elif row["cited_cov"] == 0.0:
            result["d_low"].append(row)


def audit_inline(e: dict, result: dict) -> None:
    """正文内嵌条号未登记到 statutes 的情况。"""
    registered = {st.replace("《", "").replace("》", "").replace("第", "")
                  for st in e.get("statutes") or []}
    for field in TEXT_FIELDS:
        for m in INLINE_REF.finditer(e.get(field) or ""):
            if resolve_path(m.group(1)) is None:
                continue  # 抓到的不是可识别的法名（如上文省略法名的「第 31 条」）
            ref = f"{m.group(1)}第{m.group(2)}条"
            if ref.replace("第", "") in registered:
                continue
            result["e_inline"].append({"id": e["id"], "field": field, "ref": ref,
                                       "statutes": list(e.get("statutes") or [])})


def run(root: Path) -> dict:
    result = {
        "a_missing": [], "b_rows": [], "e_inline": [], "d_high": [], "d_low": [],
        "f_no_number": [],
        "b_unknown": collections.Counter(), "c_writings": collections.defaultdict(set),
        "total_refs": 0, "entry_count": 0,
    }
    entries = load_entries(root)
    for e in entries:
        result["total_refs"] += len(e.get("statutes") or [])
        audit_entry(e, result)
        audit_inline(e, result)
    result["entry_count"] = len(entries)
    return result


def report(result: dict) -> None:
    print(f"条目 {result['entry_count']} 条，statutes 引用 {result['total_refs']} 条")
    print(f"\nA 条号不存在：{len(result['a_missing'])} 条")
    for r in result["a_missing"][:40]:
        print(f"   {r['id']} {r['subject']} | {r['ref']}")
    print(f"\nB 库外法：{sum(result['b_unknown'].values())} 条引用 / "
          f"{len(result['b_unknown'])} 种法名")
    for law, cnt in result["b_unknown"].most_common(25):
        print(f"   {cnt:4d}  {law}")
    print("\nC 同一部法多种写法：")
    for name, laws in sorted(result["c_writings"].items()):
        if len(laws) > 1:
            print(f"   {name}: {sorted(laws)}")
    print(f"\nD 语义存疑（有强候选）：{len(result['d_high'])} 条")
    for r in result["d_high"]:
        print(f"   {r['id']} {r['subject']} | {r['point'][:18]} | {r['ref']}"
              f" -> {r['alt']} (重合 {r['alt_cov']})")
    print(f"\nD 语义存疑（无强候选）：{len(result['d_low'])} 条")
    print(f"\nE 正文内嵌条号未登记：{len(result['e_inline'])} 处")
    for r in result["e_inline"][:20]:
        print(f"   {r['id']} {r['field']} | 内嵌 {r['ref']} | statutes={r['statutes']}")
    print(f"\nF 只写法名、无条号：{len(result['f_no_number'])} 条")
    for r in result["f_no_number"][:20]:
        print(f"   {r['id']} {r['subject']} | {r['ref']}")


def write_markdown(result: dict, path: Path) -> None:
    """把 A/D/E/F 类清单落成 Markdown 表格，作为核查报告附件。"""
    lines = ["# 法条引用核查清单（脚本输出）", "",
             f"- 条目 {result['entry_count']} 条，statutes 引用 {result['total_refs']} 条",
             f"- A 条号不存在：{len(result['a_missing'])}",
             f"- D 有强候选（需人工判定）：{len(result['d_high'])}",
             f"- D 无强候选：{len(result['d_low'])}",
             f"- E 正文内嵌与 statutes 不一致：{len(result['e_inline'])}",
             f"- F 只写法名无条号：{len(result['f_no_number'])}", ""]
    for title, rows, cols in (
        ("D 有强候选（需人工判定）", result["d_high"], ("id", "subject", "point", "ref", "alt")),
        ("D 无强候选", result["d_low"], ("id", "subject", "point", "ref")),
        ("A 条号不存在", result["a_missing"], ("id", "subject", "ref")),
        ("F 只写法名无条号", result["f_no_number"], ("id", "subject", "ref")),
    ):
        lines += [f"## {title}", "", "| " + " | ".join(cols) + " |",
                  "|" + "---|" * len(cols)]
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |")
        lines.append("")
    lines += ["## 库外法（无法校验）", "", "| 法名 | 引用数 |", "|---|---|"]
    for law, cnt in result["b_unknown"].most_common():
        lines.append(f"| {law} | {cnt} |")
    lines += ["", "## 同一部法的多种写法", "", "| 法条库文件 | 出现写法 |", "|---|---|"]
    for name, laws in sorted(result["c_writings"].items()):
        if len(laws) > 1:
            lines.append(f"| {name} | {'、'.join(sorted(laws))} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="全库法条引用核查（只读）")
    parser.add_argument("--json", dest="json_path", help="结果写入 JSON")
    parser.add_argument("--md", dest="md_path", help="A/D/E/F 清单写入 Markdown")
    args = parser.parse_args(argv)

    result = run(config.ROOT_DIR)
    report(result)
    if args.md_path:
        write_markdown(result, Path(args.md_path))
        print(f"\n清单已写入 {args.md_path}")
    if args.json_path:
        payload = {
            "a_missing": result["a_missing"], "b_rows": result["b_rows"],
            "f_no_number": result["f_no_number"],
            "b_unknown": dict(result["b_unknown"]), "e_inline": result["e_inline"],
            "d_high": result["d_high"], "d_low": result["d_low"],
            "c_writings": {k: sorted(v) for k, v in result["c_writings"].items()},
            "total_refs": result["total_refs"], "entry_count": result["entry_count"],
        }
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\n已写入 {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
