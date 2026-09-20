"""法条覆盖与题库核验：每部法被条目引用/被题目覆盖的覆盖率 + 判断题回源核验。

用法：
    .venv/bin/python scripts/audit_quiz_coverage.py                 # 打印摘要
    .venv/bin/python scripts/audit_quiz_coverage.py --top 30 --report ../docs/...md
    .venv/bin/python scripts/audit_quiz_coverage.py --json /tmp/cov.json

判断题回源核验分两级：
- strict：按 basis 里的「法名+条号」取到条文正文再核验数字；
- loose ：条文取不到时改用整部法文本核验（条约类前言/附件常见），报告单列。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (config, db, number_terms, quiz_bank, statute_coverage,  # noqa: E402
                 statute_index, statutes)


def judge_verification(conn) -> dict:
    """判断题回源核验：题干数字必须在依据原文里找得到。"""
    rows = conn.execute(
        "SELECT id, entry_id, subject, stem, answer, basis FROM quizzes"
        " WHERE origin=? AND status='published'", (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    library = statute_index.load_library()
    full_cache: dict[str, str] = {}
    strict_fail, loose_pass, failed = [], [], []
    for row in rows:
        if row["entry_id"]:
            entry = conn.execute("SELECT anchor, conclusion FROM v_entries WHERE id=?",
                                 (row["entry_id"],)).fetchone()
            reference = f"{entry['anchor']}。{entry['conclusion']}" if entry else ""
            mode = "entry"
        else:
            # 与出题脚本一致：先按 basis 定位到条文（条号规范化），再退回整部法文本
            located = statutes.resolve_law_article(row["basis"])
            reference = ""
            law = ""
            if located:
                law, no, sub = located
                article = library[law].article(no, sub) if law in library else None
                reference = article.text if article else ""
            if law and law not in full_cache:
                path = config.STATUTE_DIR / f"{law}.md"
                full_cache[law] = path.read_text(encoding="utf-8-sig") if path.exists() else ""
            mode = "statute"
        if reference and number_terms.is_grounded(row["stem"], reference, row["answer"])[0]:
            continue
        if mode == "statute" and full_cache.get(law):
            ok, _why = number_terms.is_grounded(row["stem"], full_cache[law],
                                                row["answer"])
            if ok:
                loose_pass.append(row["id"])
                continue
        failed.append({"id": row["id"], "subject": row["subject"],
                       "stem": row["stem"], "basis": row["basis"]})
    return {"total": len(rows), "loose": len(loose_pass), "failed": failed,
            "loose_ids": loose_pass}


def report_markdown(rows: list[dict], summ: dict, verify: dict, top: int) -> str:
    lines = [
        "# 法条覆盖与题库核验报告（自动生成）",
        "",
        "## 1. 总量",
        "",
        f"- 法条库文件 **{summ['total']['laws']}** 部 / 条文 **{summ['total']['articles']}** 条",
        f"- 被题目覆盖条文 **{summ['total']['covered']}** 条，"
        f"总覆盖率 **{summ['total']['coverage'] * 100:.1f}%**",
        f"- 有题目覆盖的法 **{summ['total']['laws_with_question']}** 部"
        f"（共 {summ['total']['laws']} 部）",
        f"- 被条目引用过的条文 **{summ['total']['cited']}** 条",
        "",
        "## 2. 分类",
        "",
        "| 类别 | 法数 | 有题法数 | 条文数 | 已覆盖 | 覆盖率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, bucket in sorted(summ["by_category"].items(),
                               key=lambda kv: -kv[1]["articles"]):
        rate = bucket["covered"] / bucket["articles"] if bucket["articles"] else 0
        lines.append(f"| {name} | {bucket['laws']} | {bucket['laws_with_question']} |"
                     f" {bucket['articles']} | {bucket['covered']} | {rate * 100:.1f}% |")
    lines += ["", f"## 3. 覆盖率最低的 {top} 部法", "",
              "| 法名 | 类别 | 条文 | 已覆盖 | 覆盖率 |", "|---|---|---:|---:|---:|"]
    for row in rows[:top]:
        lines.append(f"| {row['name']} | {row['category']} | {row['articles']} |"
                     f" {row['covered']} | {row['coverage'] * 100:.1f}% |")
    lines += [
        "",
        "## 4. 数字判断题回源核验",
        "",
        f"- 判断题总数 {verify['total']}，strict 不通过但全文核验通过（loose）"
        f" **{verify['loose']}** 条",
        f"- strict 与 loose 都不通过 **{len(verify['failed'])}** 条",
    ]
    if verify["failed"]:
        lines += ["", "| 题目 | 科目 | 题干 | 依据 |", "|---:|---|---|---|"]
        for item in verify["failed"][:top]:
            lines.append(f"| {item['id']} | {item['subject']} | {item['stem'][:40]} |"
                         f" {item['basis']} |")
    lines += ["", "## 5. 复现", "", "```bash",
              ".venv/bin/python scripts/audit_quiz_coverage.py --top 30 --report ../docs/superpowers/research/2026-09-20-法条覆盖与题库核验报告.md",
              "```", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="法条覆盖率与判断题核验")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--report", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--no-verify", action="store_true", help="跳过判断题回源核验")
    args = ap.parse_args(argv)

    conn = db.connect()
    rows = statute_coverage.coverage(conn)
    summ = statute_coverage.summary(rows)
    verify = {"total": 0, "loose": 0, "failed": [], "loose_ids": []}
    if not args.no_verify:
        verify = judge_verification(conn)
    print(f"法 {summ['total']['laws']} 部 / 条文 {summ['total']['articles']} 条；"
          f"已被题目覆盖 {summ['total']['covered']} 条"
          f"（{summ['total']['coverage'] * 100:.1f}%），"
          f"有题法 {summ['total']['laws_with_question']}/{summ['total']['laws']}")
    for name, bucket in sorted(summ["by_category"].items(),
                               key=lambda kv: -kv[1]["articles"]):
        rate = bucket["covered"] / bucket["articles"] if bucket["articles"] else 0
        print(f"  - {name}: {bucket['laws_with_question']}/{bucket['laws']} 部有题，"
              f"条文覆盖 {rate * 100:.1f}%")
    print(f"判断题核验：{verify['total']} 题，loose {verify['loose']}，"
          f"不通过 {len(verify['failed'])}")
    print(f"覆盖率最低的 {args.top} 部：")
    for row in rows[:args.top]:
        print(f"  - {row['name']} {row['covered']}/{row['articles']}"
              f"（{row['coverage'] * 100:.1f}%）")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"summary": summ, "laws": rows, "verify": verify},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON -> {args.json}")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            report_markdown(rows, summ, verify, args.top), encoding="utf-8")
        print(f"报告 -> {args.report}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
