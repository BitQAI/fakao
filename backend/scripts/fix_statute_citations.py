"""修正全库法条引用中**已逐条读原文确认**的高置信错配条号。

用法：
    python scripts/fix_statute_citations.py            # dry-run，只打印将做的改动
    python scripts/fix_statute_citations.py --apply    # 写回 data/entries/*.json

判定依据见 docs/superpowers/specs/2026-09-15-法条引用核查-design.md：
现引条文与条目考点/结论无实质重合，且库内唯一候选条文原文完整包含该结论所述规则。
只改条号，不改结论的法律规则表述；正文内嵌的同一串条号同步替换。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402

TEXT_FIELDS = ("conclusion", "note", "tts_text")
REF_RE = re.compile(r"^(?P<law>.*?)第?(?P<num>[\d零一二三四五六七八九十百千]+)条$")

# {条目ID: {"statutes": [(旧串, 新串|None)], "text": [(旧串, 新串)]}}
# None 表示删除该条引用（重复引用/错误引用）
FIXES = {
    # ── 民诉法：2021/2023 修正后条号位移 ─────────────────────────────
    "MS-037": {"statutes": [("民诉法216条", "民诉法222条")]},
    "MS-038": {"statutes": [("民诉法207条", "民诉法217条")]},
    "MS-040": {"statutes": [("民诉法231条", None)]},
    "MS-076": {"statutes": [("民诉法44条", "民诉法47条")]},
    "MS-077": {"statutes": [("民诉法44条", "民诉法47条")]},
    "MS-078": {"statutes": [("民诉法45条", "民诉法48条")]},
    "MS-081": {"statutes": [("民诉法121条", "民诉法151条")]},
    "MS-135": {"statutes": [("民诉法第78条", "民诉法第81条")],
               "text": [("民诉法第78条", "民诉法第81条")]},
    "MS-136": {"statutes": [("民诉法第79条", "民诉法第82条")],
               "text": [("民诉法第79条", "民诉法第82条")]},
    "MS-139": {"statutes": [("民诉法第82条", "民诉法第85条")],
               "text": [("民诉法第82条", "民诉法第85条")]},
    "MS-140": {"statutes": [("民诉法第83条", "民诉法第86条")],
               "text": [("民诉法第83条", "民诉法第86条")]},
    "MS-148": {"statutes": [("民诉法211条", "民诉法219条")]},
    "MS-173": {"statutes": [("民诉法161条", "民诉法164条")]},
    "MS-178": {"statutes": [("民诉法167条", "民诉法171条")]},
    "MS-179": {"statutes": [("民诉法168条", "民诉法157条")]},
    "MS-180": {"statutes": [("民诉法167条", "民诉法59条")]},
    "MS-181": {"statutes": [("民诉法170条", "民诉法180条")]},
    "MS-182": {"statutes": [("民诉法171条", "民诉法176条")]},
    "MS-189": {"statutes": [("民诉法203条", "民诉法217条")]},
    "MS-192": {"statutes": [("民诉法203条", "民诉法211条")]},
    "MS-193": {"statutes": [("民诉法203条", "民诉法211条")]},
    "MS-195": {"statutes": [("民诉法211条", "民诉法219条")]},
    "MS-196": {"statutes": [("民诉法211条", "民诉法220条")]},
    "MS-197": {"statutes": [("民诉法180条", "民诉法184条")]},
    "MS-198": {"statutes": [("民诉法180条", "民诉法185条")]},
    "MS-200": {"statutes": [("民诉法203条", "民诉法207条")]},
    "MS-207": {"statutes": [("民诉法228条", "民诉法238条"), ("民诉法230条", None)]},
    "MS-227": {"statutes": [("民诉法232条", "民诉法236条"), ("民诉法234条", "民诉法238条")]},
    "MS-233": {"statutes": [("民诉法232条", "民诉法238条")]},
    "MS-234": {"statutes": [("民诉法232条", "民诉法238条")]},
    # ── 民诉法涉外编：2023 修正后整体 +4 ────────────────────────────
    "MS-098": {"statutes": [("民诉法273条", "民诉法277条")]},
    "MS-212": {"statutes": [("民诉法第272条", "民诉法第276条")]},
    "MS-213": {"statutes": [("民诉法第273条", "民诉法第277条")]},
    "MS-214": {"statutes": [("民诉法第275条", "民诉法第279条")]},
    "MS-217": {"statutes": [("民诉法第278条", "民诉法第283条")]},
    # ── 刑诉法 ──────────────────────────────────────────────────
    "XS-047": {"statutes": [("刑诉法第292条", None)]},
    "XS-076": {"statutes": [("刑诉法66条", "刑诉法68条")],
               "text": [("刑诉法第66条", "刑诉法第68条")]},
    "XS-242": {"statutes": [("刑诉法第272条", "刑诉法第273条")]},
    # ── 新公司法（2023 条号重排）────────────────────────────────
    "SJ-028": {"statutes": [("公司法249条", "公司法250条")],
               "text": [("新公司法第249条", "新公司法第250条")]},
    "SJ-032": {"statutes": [("公司法264条", "公司法263条")],
               "text": [("新公司法第264条", "新公司法第263条")]},
    "SJ-118": {"statutes": [("公司法83条", "公司法76条")]},
    "SJ-132": {"statutes": [("公司法88条", "公司法90条")]},
    "SJ-557": {"statutes": [("公司法46条", "公司法67条")],
               "text": [("公司法第46条", "公司法第67条")]},
    "SJ-558": {"statutes": [("公司法53条", "公司法78条")],
               "text": [("公司法第53条", "公司法第78条")]},
    "SJ-559": {"statutes": [("公司法49条", "公司法74条")],
               "text": [("公司法第49条", "公司法第74条")]},
    # ── 三国法：涉外编整体位移（2021 旧编号）────────────────────
    "SG-064": {"statutes": [("民诉法第272条", "民诉法第276条")],
               "text": [("民诉法第272条", "民诉法第276条")]},
    "SG-066": {"statutes": [("民诉法第274条", "民诉法第278条")],
               "text": [("民诉法第274条", "民诉法第278条")]},
    "SG-067": {"statutes": [("民诉法第275条", "民诉法第279条")],
               "text": [("民诉法第275条", "民诉法第279条")]},
    "SG-069": {"statutes": [("民诉法第289条", "民诉法第298条")],
               "text": [("民诉法第289条", "民诉法第298条")]},
    # ── 行政复议法 / 行政许可法 ─────────────────────────────────
    "XZ-040": {"statutes": [("行政复议法9条", "行政复议法20条")]},
    "XZ-087": {"statutes": [("行政许可法48条", "行政许可法47条")]},
}


def text_pairs(rules: dict) -> list[tuple[str, str]]:
    """显式 text 规则 + 由 statutes 规则自动派生的正文条号（带法名）替换。"""
    pairs = list(rules.get("text", []))
    for old, new in rules.get("statutes", []):
        if new is None:
            continue
        m_old, m_new = REF_RE.match(old), REF_RE.match(new)
        if not (m_old and m_new):
            continue
        law, num_old, num_new = m_old.group("law"), m_old.group("num"), m_new.group("num")
        for form in (f"{law}第{num_old}条", f"{law}{num_old}条"):
            pair = (form, form.replace(num_old, num_new))
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def load_all(root: Path) -> tuple[dict[str, dict], dict[str, Path]]:
    by_id, where = {}, {}
    for path in sorted((root / "data/entries").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for e in data["entries"]:
            by_id[e["id"]] = e
            where[e["id"]] = path
    return by_id, where


def apply_entry(e: dict, rules: dict) -> list[str]:
    """就地修改条目，返回改动说明。"""
    changes = []
    statutes = list(e.get("statutes") or [])
    for old, new in rules.get("statutes", []):
        if old not in statutes:
            if new is None or new in statutes:
                continue  # 幂等：已应用过
            raise ValueError(f"{e['id']}: statutes 中找不到 {old}")
        i = statutes.index(old)
        if new is None:
            statutes.pop(i)
            changes.append(f"statutes 删除 {old}")
        else:
            statutes[i] = new
            changes.append(f"statutes {old} → {new}")
    seen, deduped = set(), []
    for st in statutes:
        if st and st not in seen:
            seen.add(st)
            deduped.append(st)
    e["statutes"] = deduped
    for old, new in text_pairs(rules):
        for field in TEXT_FIELDS:
            value = e.get(field) or ""
            if old in value:
                e[field] = value.replace(old, new)
                changes.append(f"{field} 内嵌 {old} → {new}")
    return changes


def self_check(by_id: dict) -> list[str]:
    problems = []
    for eid in FIXES:
        e = by_id.get(eid)
        if e is None:
            problems.append(f"{eid}: 条目不存在")
            continue
        sts = e.get("statutes") or []
        if not sts:
            problems.append(f"{eid}: statutes 为空")
        if len(sts) != len(set(sts)):
            problems.append(f"{eid}: statutes 有重复 {sts}")
        for old, _ in text_pairs(FIXES[eid]):
            for field in TEXT_FIELDS:
                if old in (e.get(field) or ""):
                    problems.append(f"{eid}: {field} 仍含旧串 {old}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="修正高置信法条引用错配")
    parser.add_argument("--apply", action="store_true", help="写回 JSON（默认 dry-run）")
    args = parser.parse_args(argv)

    by_id, where = load_all(config.ROOT_DIR)
    missing = [eid for eid in FIXES if eid not in by_id]
    if missing:
        print(f"错误：{len(missing)} 个条目未找到 {missing}", file=sys.stderr)
        return 1

    touched: dict[Path, int] = {}
    for eid, rules in FIXES.items():
        e = by_id[eid]
        for line in apply_entry(e, rules):
            print(f"  {eid} {e.get('subject')} | {line}")
        touched[where[eid]] = touched.get(where[eid], 0) + 1

    print(f"\n共 {len(FIXES)} 条条目，涉及 {len(touched)} 个文件")
    for path, cnt in sorted(touched.items()):
        print(f"  {path.name}: {cnt} 条")

    if not args.apply:
        print("\n（dry-run，未写回；加 --apply 执行）")
        return 0

    for path in sorted(touched):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["entries"] = [by_id[e["id"]] for e in data["entries"]]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写回 JSON")

    problems = self_check(by_id)
    if problems:
        print("自检未通过：", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("自检通过：条号非空、无重复、正文无旧串残留")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
