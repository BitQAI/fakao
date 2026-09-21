"""法条题入口覆盖审计：自测 / 看背 / 听学 / 法条页 各自能触达哪些法条驱动题。

口径（2026-09-20 卡片条目化后）：
- 客观题（`origin='bank'`）→ 重建为卡片条目（`entries.kind='card'`），
  看背 / 听学 / 自测 / 法条页四个入口都能练；卡片与题目 **1:1**。
- 判断题（`origin='judge'`）**不进看背 / 听学**（用户口径），只在自测与法条页出现。

用法：
    .venv/bin/python scripts/audit_quiz_entrypoints.py
    .venv/bin/python scripts/audit_quiz_entrypoints.py --report ../docs/…md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (card_entries, config, db, quiz_bank, statute_cards,  # noqa: E402
                 statute_index, statutes)

ALL_ORIGINS = (quiz_bank.ORIGIN_BANK, quiz_bank.ORIGIN_JUDGE)


def universe(conn, origins=ALL_ORIGINS) -> set[int]:
    """法条驱动题（已发布、不挂条目、有依据）。"""
    rows = conn.execute(
        f"SELECT id FROM quizzes WHERE origin IN ({','.join('?' * len(origins))})"
        " AND status='published'"
        " AND entry_id IS NULL AND basis != ''",
        origins).fetchall()
    return {r["id"] for r in rows}


def reachable_by_quiz_pool(conn) -> set[int]:
    """自测：法条卡池（含判断题，不带 limit 即全量）。"""
    return {c["quiz_id"] for c in statute_cards.pool(conn, mode="quiz", limit=0)}


def reachable_by_card_entries(conn) -> set[int]:
    """看背 / 听学：卡片条目池（kind='card' ∧ status='final'）反查 quiz_id。"""
    rows = conn.execute(
        "SELECT id FROM entries WHERE kind='card' AND status='final'").fetchall()
    return {q for q in (card_entries.quiz_id_of(r["id"]) for r in rows)
            if q is not None}


def reachable_by_statute_page(conn) -> set[int]:
    """法条页：basis 能定位到「法条库某条」的题才挂得上。"""
    out: set[int] = set()
    library = statute_index.load_library(config.STATUTE_DIR)
    rows = conn.execute(
        "SELECT id, basis FROM quizzes WHERE origin IN (?,?) AND status='published'"
        " AND entry_id IS NULL AND basis != ''", ALL_ORIGINS).fetchall()
    for row in rows:
        located = statutes.resolve_law_article(row["basis"])
        if located is None:
            continue
        law_key, no, sub = located
        law = library.get(law_key)
        if law is not None and law.article(no, sub) is not None:
            out.add(row["id"])
    return out


def reachable_by_card_pool(conn, mode: str) -> set[int]:
    """兼容旧调用：按模式取法条卡池（不带 limit 即全量）。"""
    return {c["quiz_id"] for c in statute_cards.pool(conn, mode=mode, limit=0)}


def audit(conn) -> dict:
    bank = universe(conn, (quiz_bank.ORIGIN_BANK,))
    everything = universe(conn)
    cards = reachable_by_card_entries(conn)
    checks = [
        ("看背", bank, cards),
        ("听学", bank, cards),
        ("自测（今日）", everything, reachable_by_quiz_pool(conn)),
        ("法条页", everything, reachable_by_statute_page(conn)),
    ]
    rows = []
    for name, scope, ids in checks:
        missing = scope - ids
        rows.append({"entry": name, "scope": len(scope),
                     "reachable": len(ids & scope),
                     "missing": len(missing),
                     "missing_ids": sorted(missing)[:5],
                     "ok": not missing})
    orphan = bank - cards          # 客观题没有卡片
    extra = cards - bank           # 卡片没有对应客观题
    return {"total": len(everything), "bank": len(bank),
            "judge": len(everything) - len(bank), "entries": rows,
            "cards": card_entries.stats(conn),
            "card_orphan": sorted(orphan)[:5], "card_extra": sorted(extra)[:5],
            "card_ok": not orphan and not extra,
            "pool": statute_cards.stats(conn),
            "ok": all(r["ok"] for r in rows) and not orphan and not extra}


def report_markdown(result: dict) -> str:
    lines = ["# 法条题入口覆盖报告（自动生成）", "",
             f"- 已发布法条驱动题 **{result['total']}** 题"
             f"（客观题 {result['bank']} / 判断题 {result['judge']}）",
             f"- 卡片条目 **{result['cards']['cards']}** 张"
             f"（final {result['cards']['final']}）↔ 客观题 1:1："
             f"{'✅' if result['card_ok'] else '❌'}",
             f"- 正式条目 {result['cards']['entries']} 条；"
             f"法条卡池 {result['pool']['total']} 题"
             f"（看背已看 {result['pool']['seen'].get('read', 0)}，"
             f"听学已听 {result['pool']['seen'].get('listen', 0)}，"
             f"自测已练 {result['pool']['seen'].get('quiz', 0)}）", "",
             "| 入口 | 覆盖口径 | 应有 | 可触达 | 缺口 | 结论 |",
             "|---|---|---:|---:|---:|---|"]
    for row in result["entries"]:
        scope = "全部（含判断题）" if row["scope"] >= result["total"] else "客观题（题卡口径）"
        lines.append(f"| {row['entry']} | {scope} | {row['scope']} | {row['reachable']} | "
                     f"{row['missing']} | {'✅ 全覆盖' if row['ok'] else '❌ 有缺口'} |")
    lines += ["",
              "口径说明：看背 / 听学只做题卡（客观题），判断题按用户口径不进这两个入口；"
              "自测与法条页覆盖全部已发布法条驱动题。"
              "轮转按「未看过 / 未听过优先」排序，取过的排到队尾，多次取队列可逐步取尽"
              "（单测 `test_pool_repeated_rounds_can_exhaust_all`）。", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="法条题四入口覆盖审计")
    ap.add_argument("--report", default=None, help="写 Markdown 报告到该路径")
    args = ap.parse_args(argv)

    conn = db.connect()
    result = audit(conn)
    conn.close()
    print(f"已发布法条驱动题 {result['total']} 题"
          f"（客观题 {result['bank']} / 判断题 {result['judge']}）")
    print(f"卡片条目 {result['cards']['cards']} 张 ↔ 客观题 1:1："
          f"{'OK' if result['card_ok'] else '异常 ' + str(result['card_orphan'] + result['card_extra'])}")
    for row in result["entries"]:
        flag = "OK " if row["ok"] else "缺口"
        print(f"  {flag} {row['entry']:10s} 应有 {row['scope']:6d}"
              f" 可触达 {row['reachable']:6d}"
              f" 缺 {row['missing']:4d} {row['missing_ids'] or ''}")
    if args.report:
        Path(args.report).write_text(report_markdown(result), encoding="utf-8")
        print("报告 ->", args.report)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
