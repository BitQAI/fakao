"""法条题入口覆盖审计：自测 / 看背 / 听学 / 法条页 是否都能触达全部法条驱动题。

「完整覆盖」的可验证定义：入口的候选池 ⊇ 全部已发布法条驱动题
（`quizzes.entry_id IS NULL AND status='published'`），且轮转（未看过优先）能逐步取尽。

用法：
    .venv/bin/python scripts/audit_quiz_entrypoints.py
    .venv/bin/python scripts/audit_quiz_entrypoints.py --report ../docs/…md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, quiz_bank, statute_cards, statute_index, statutes  # noqa: E402

#: 四个入口：名称 → (模式, 取数方式)
ENTRIES = (
    ("自测（今日）", "quiz"),
    ("看背", "read"),
    ("听学", "listen"),
)


def universe(conn) -> set[int]:
    """全量法条驱动题（已发布、不挂条目、有依据）。"""
    rows = conn.execute(
        "SELECT id FROM quizzes WHERE origin IN (?,?) AND status='published'"
        " AND entry_id IS NULL AND basis != ''",
        (quiz_bank.ORIGIN_BANK, quiz_bank.ORIGIN_JUDGE)).fetchall()
    return {r["id"] for r in rows}


def reachable_by_card_pool(conn, mode: str) -> set[int]:
    """自测/看背/听学：走同一份法条卡池（不带 limit 即全量）。"""
    return {c["quiz_id"] for c in statute_cards.pool(conn, mode=mode, limit=0)}


def reachable_by_statute_page(conn) -> set[int]:
    """法条页：basis 能定位到「法条库某条」的题才挂得上。"""
    out: set[int] = set()
    library = statute_index.load_library(config.STATUTE_DIR)
    rows = conn.execute(
        "SELECT id, basis FROM quizzes WHERE origin IN (?,?) AND status='published'"
        " AND entry_id IS NULL AND basis != ''",
        (quiz_bank.ORIGIN_BANK, quiz_bank.ORIGIN_JUDGE)).fetchall()
    for row in rows:
        located = statutes.resolve_law_article(row["basis"])
        if located is None:
            continue
        law_key, no, sub = located
        law = library.get(law_key)
        if law is not None and law.article(no, sub) is not None:
            out.add(row["id"])
    return out


def audit(conn) -> dict:
    total = universe(conn)
    checks = [(name, reachable_by_card_pool(conn, mode)) for name, mode in ENTRIES]
    checks.append(("法条页", reachable_by_statute_page(conn)))
    rows = []
    for name, ids in checks:
        missing = total - ids
        rows.append({"entry": name, "reachable": len(ids & total),
                     "missing": len(missing),
                     "missing_ids": sorted(missing)[:5],
                     "ok": not missing})
    return {"total": len(total), "entries": rows,
            "pool": statute_cards.stats(conn), "ok": all(r["ok"] for r in rows)}


def report_markdown(result: dict) -> str:
    lines = ["# 法条题入口覆盖报告（自动生成）", "",
             f"- 法条驱动题（已发布）**{result['total']}** 题",
             f"- 法条卡池：{result['pool']['total']} 张"
             f"（看背已看 {result['pool']['seen'].get('read', 0)}，"
             f"听学已听 {result['pool']['seen'].get('listen', 0)}，"
             f"自测已练 {result['pool']['seen'].get('quiz', 0)}）", "",
             "| 入口 | 可触达 | 缺口 | 结论 |", "|---|---:|---:|---|"]
    for row in result["entries"]:
        lines.append(f"| {row['entry']} | {row['reachable']} | {row['missing']} | "
                     f"{'✅ 全覆盖' if row['ok'] else '❌ 有缺口'} |")
    lines += ["", "口径：候选池 ⊇ 全部已发布法条驱动题即算「完整覆盖」；"
              "轮转按「未看过优先」排序，看/听/练过的题会排到队尾，"
              "因此多次取队列可逐步取尽（单测 `test_pool_repeated_rounds_can_exhaust_all`）。", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="法条题四入口覆盖审计")
    ap.add_argument("--report", default=None, help="写 Markdown 报告到该路径")
    args = ap.parse_args(argv)

    conn = db.connect()
    result = audit(conn)
    conn.close()
    print(f"法条驱动题 {result['total']} 题；四入口覆盖：")
    for row in result["entries"]:
        flag = "OK " if row["ok"] else "缺口"
        print(f"  {flag} {row['entry']:10s} 可触达 {row['reachable']:6d}"
              f" 缺 {row['missing']:4d} {row['missing_ids'] or ''}")
    if args.report:
        Path(args.report).write_text(report_markdown(result), encoding="utf-8")
        print("报告 ->", args.report)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
