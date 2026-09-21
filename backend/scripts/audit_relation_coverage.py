"""关系型判断题覆盖审计：哪部法、哪个词族、哪些条目还没出题。

口径：
- 法条侧分母 = 含关系词的条文（`app.relation_terms.families_of` 非空）
- 法条侧分子 = 已有非数字型判断题（`origin='judge' AND variant NOT IN ('','number')`）的条文
- 条目侧分母 = 「场景 + 结论」含关系词的 final 条目

用法：
    .venv/bin/python scripts/audit_relation_coverage.py --top 30
    .venv/bin/python scripts/audit_relation_coverage.py \\
        --report ../docs/superpowers/research/2026-09-21-关系型判断题覆盖报告.md
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (config, db, quiz_bank, relation_terms, statute_index,  # noqa: E402
                 statutes)
from scripts.build_judge_bank import article_blocks  # noqa: E402

RELATION_VARIANTS = tuple(f for f in relation_terms.FAMILY_ORDER)
_NOISE_RE = re.compile(r"[\s*#>　]+")


def _norm(text: str) -> str:
    """去掉空白与 Markdown 噪声，用于比对「文件切块」与「法条库索引」是否同一段原文。"""
    return _NOISE_RE.sub("", text or "")


def check_question(stem: str, text: str, answer: str) -> tuple[bool, str]:
    """按「出题时的口径」复核一道题。

    「对」题直接走闸门；「错」题出题时会把依据收缩到含目标词的那一句（避免截断长条文），
    复核面对的是全文，因此不能要求「原文只少一个关系词」——否则会把合法题误判为不通过。
    """
    if answer != "错":
        return relation_terms.check(stem, text, answer)
    stem_terms = relation_terms.terms_of(stem)
    text_terms = relation_terms.terms_of(text)
    extra = stem_terms - text_terms
    if not extra:
        return False, "「错」题未偷换关系词"
    if len(extra) > 1:
        return False, f"「错」题偷换 {len(extra)} 处关系词（上限 1）"
    new_term = next(iter(extra))
    if not any(new_term in relation_terms.swaps_for(term) for term in text_terms):
        return False, f"原文里没有可偷换成「{new_term}」的关系词"
    unmatched = relation_terms.subject_terms(stem) - relation_terms.subject_terms(text)
    if unmatched:
        return False, "题干主体未在原文出现：" + "、".join(sorted(unmatched))
    return True, ""


def statute_totals() -> dict:
    """法条侧分母：{(法, 条号)} 与按族计数。"""
    articles: set[tuple[str, int]] = set()
    by_family = collections.Counter()
    by_law = collections.Counter()
    for path in sorted(config.STATUTE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        for no, body in article_blocks(text):
            families = relation_terms.families_of(body)
            if not families:
                continue
            articles.add((path.stem, no))
            for family in families:
                by_family[family] += 1
            by_law[path.stem] += 1
    return {"articles": articles, "by_family": by_family, "by_law": by_law}


def covered_statutes(conn) -> dict:
    """法条侧分子：已出题的条文（去掉条目侧与数字题）。"""
    rows = conn.execute(
        "SELECT basis, variant, status FROM quizzes WHERE origin=?"
        " AND entry_id IS NULL AND basis != '' AND variant NOT IN ('', 'number')",
        (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    articles: set[tuple[str, int]] = set()
    by_family = collections.Counter()
    by_law = collections.Counter()
    by_status = collections.Counter()
    for row in rows:
        by_status[row["status"]] += 1
        located = statutes.resolve_law_article(row["basis"])
        if located is None:
            continue
        law_key, no, _sub = located
        articles.add((law_key, no))
        by_family[row["variant"]] += 1
        by_law[law_key] += 1
    return {"articles": articles, "by_family": by_family, "by_law": by_law,
            "by_status": by_status}


def entry_totals(conn) -> set[str]:
    rows = conn.execute(
        "SELECT id, anchor, conclusion FROM v_entries WHERE status='final'").fetchall()
    return {r["id"] for r in rows
            if relation_terms.families_of(f"{r['anchor']}。{r['conclusion']}")}


def covered_entries(conn) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT entry_id FROM quizzes WHERE origin=? AND entry_id IS NOT NULL"
        " AND variant NOT IN ('', 'number')", (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    return {r["entry_id"] for r in rows}


def _pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "-"


def verify_questions(conn) -> dict:
    """回源复核：把每条已生成的法条侧关系题，重新用闸门对一遍**出题时用的那段原文**。

    不调用 LLM：basis → 法条库文件切块 → `relation_terms.check`。用于抽检之外的兜底核验。
    同时统计「文件内第X条」与「法条库索引第X条」内容不一致的条数（老问题：影响 basis 跳转）。
    """
    rows = conn.execute(
        "SELECT id, basis, stem, answer, variant FROM quizzes WHERE origin=?"
        " AND entry_id IS NULL AND basis != '' AND variant NOT IN ('', 'number')"
        " AND status != 'archived'", (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    library = statute_index.load_library()
    passed = 0
    failures: list[tuple[int, str, str]] = []
    numbering_gaps: list[tuple[str, int]] = []
    blocks_cache: dict[str, dict] = {}
    for row in rows:
        located = statutes.resolve_law_article(row["basis"])
        if located is None:
            failures.append((row["id"], "basis/条文解析失败", row["stem"]))
            continue
        law_key, no, sub = located
        path = config.STATUTE_DIR / f"{law_key}.md"
        if not path.exists():
            failures.append((row["id"], "法条库文件缺失", row["stem"]))
            continue
        if law_key not in blocks_cache:
            blocks_cache[law_key] = dict(
                article_blocks(path.read_text(encoding="utf-8-sig")))
        text = blocks_cache[law_key].get(no)
        if not text:
            failures.append((row["id"], "条文切块缺失", row["stem"]))
            continue
        law = library.get(law_key)
        article = law.article(no, sub) if law else None
        library_text = article.text if article is not None else ""
        if library_text and _norm(library_text) != _norm(text):
            numbering_gaps.append((law_key, no))
        # 两种原文（文件切块 / 法条库索引）任一通过即算通过：
        # 法条侧出题用文件切块，配对补题用 `statutes` 库索引，两者在个别文件上条号错位
        ok, why = check_question(row["stem"], text, row["answer"])
        if not ok and library_text:
            ok, why = check_question(row["stem"], library_text, row["answer"])
        if ok:
            passed += 1
        else:
            failures.append((row["id"], why, row["stem"]))
    # 条目侧：依据原文 = 「场景 + 结论」，与出题时同一拼接口径
    entry_rows = conn.execute(
        "SELECT q.id, q.stem, q.answer, e.anchor, e.conclusion FROM quizzes q"
        " JOIN v_entries e ON e.id = q.entry_id WHERE q.origin=?"
        " AND q.entry_id IS NOT NULL AND q.variant NOT IN ('', 'number')"
        " AND q.status != 'archived'", (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    entry_passed = 0
    for row in entry_rows:
        text = f"{row['anchor']}。{row['conclusion']}"
        ok, why = check_question(row["stem"], text, row["answer"])
        if ok:
            entry_passed += 1
        else:
            failures.append((row["id"], f"条目侧：{why}", row["stem"]))
    return {"total": len(rows), "passed": passed, "failures": failures,
            "numbering_gaps": numbering_gaps,
            "entry_total": len(entry_rows), "entry_passed": entry_passed}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="关系型判断题覆盖审计")
    ap.add_argument("--top", type=int, default=20, help="缺口最多的前 N 部法")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--verify", action="store_true",
                    help="回源复核已生成的关系题（法条原文 + 闸门重跑）")
    ap.add_argument("--archive-failed", action="store_true",
                    help="把回源复核不通过的题置为 archived（可逆）")
    ap.add_argument("--sample", type=int, default=0,
                    help="报告里每个词族附 N 道样例题，供人工抽检")
    args = ap.parse_args(argv)

    conn = db.connect()
    totals = statute_totals()
    covered = covered_statutes(conn)
    ent_total = entry_totals(conn)
    ent_covered = covered_entries(conn)

    art_total = len(totals["articles"])
    art_cov = len(totals["articles"] & covered["articles"])
    print(f"法条侧：含关系词条文 {art_total}，已出题 {art_cov}"
          f"（{_pct(art_cov, art_total)}）")
    print(f"条目侧：含关系词条目 {len(ent_total)}，已出题 {len(ent_covered)}"
          f"（{_pct(len(ent_covered), len(ent_total))}）")
    pending = covered["by_status"].get("draft", 0)
    published = covered["by_status"].get("published", 0)
    print(f"关系题状态：draft {pending} / published {published}"
          f" / archived {covered['by_status'].get('archived', 0)}")

    rows = []
    for family in RELATION_VARIANTS:
        total = totals["by_family"].get(family, 0)
        done = covered["by_family"].get(family, 0)
        rows.append((family, total, done))
    print("词族覆盖:", json.dumps({f: f"{d}/{t}" for f, t, d in rows},
                                  ensure_ascii=False))

    gaps = sorted(totals["by_law"].items(),
                  key=lambda kv: -(kv[1] - covered["by_law"].get(kv[0], 0)))
    gap_rows = [(law, total, covered["by_law"].get(law, 0)) for law, total in gaps
                if total > covered["by_law"].get(law, 0)][:args.top]
    print(f"缺口最大的 {len(gap_rows)} 部法:")
    for law, total, done in gap_rows:
        print(f"  {law[:32]:<34} {done}/{total}")

    verified = verify_questions(conn) if args.verify else None
    samples: dict[str, list] = {}
    if args.sample:
        for family in RELATION_VARIANTS:
            rows = conn.execute(
                "SELECT id, subject, stem, answer, analysis, basis FROM quizzes"
                " WHERE origin=? AND variant=? AND status != 'archived'"
                " ORDER BY RANDOM() LIMIT ?",
                (quiz_bank.ORIGIN_JUDGE, family, args.sample)).fetchall()
            samples[family] = [dict(r) for r in rows]
    if verified:
        print(f"回源复核：{verified['passed']}/{verified['total']} 通过"
              f"（法条侧）；条目侧 {verified['entry_passed']}"
              f"/{verified['entry_total']}；不通过共 {len(verified['failures'])}）")
        gaps = verified["numbering_gaps"]
        print(f"条号口径差异（文件「第X条」≠ 法条库索引第X条）：{len(gaps)} 条")
        for qid, why, stem in verified["failures"][:10]:
            print(f"  ✗ {qid} {why} | {stem[:36]}")
        if args.archive_failed and verified["failures"]:
            ids = [qid for qid, _why, _stem in verified["failures"]]
            conn.executemany("UPDATE quizzes SET status='archived' WHERE id=?",
                             [(qid,) for qid in ids])
            conn.commit()
            print(f"已归档回源不通过的 {len(ids)} 题（改回 published 即恢复）")

    if args.report:
        lines = ["# 关系型判断题覆盖报告", "",
                 f"- 法条侧：含关系词条文 {art_total}，已出题 {art_cov}"
                 f"（{_pct(art_cov, art_total)}）",
                 f"- 条目侧：含关系词条目 {len(ent_total)}，已出题 {len(ent_covered)}"
                 f"（{_pct(len(ent_covered), len(ent_total))}）",
                 f"- 关系题状态：draft {pending} / published {published}"
                 f" / archived {covered['by_status'].get('archived', 0)}", "",
                 "## 词族覆盖（已出题/含该族条文）", "",
                 "| 词族 | 覆盖 | 条文总数 |", "|---|---|---|"]
        lines += [f"| {f} | {d} | {t} |" for f, t, d in sorted(
            rows, key=lambda r: (r[2] / r[1]) if r[1] else 1)]
        lines += ["", f"## 缺口最大的 {len(gap_rows)} 部法", "",
                  "| 法 | 已出题 | 含关系词条文 |", "|---|---|---|"]
        lines += [f"| {law} | {done} | {total} |" for law, total, done in gap_rows]
        if verified:
            lines += ["", "## 回源复核（法条原文 + 闸门重跑）", "",
                      f"- 法条侧通过 {verified['passed']} / {verified['total']}",
                      f"- 条目侧通过 {verified['entry_passed']}"
                      f" / {verified['entry_total']}",
                      f"- 不通过 {len(verified['failures'])}",
                      f"- 条号口径差异（文件「第X条」≠ 法条库索引第X条）："
                      f"{len(verified['numbering_gaps'])} 条", ]
            lines += [f"  - {qid}：{why}（{stem[:36]}）"
                      for qid, why, stem in verified["failures"][:50]]
        if samples:
            lines += ["", "## 分层抽检样例题", ""]
            for family, items in samples.items():
                if not items:
                    continue
                lines += [f"### {family}", ""]
                for r in items:
                    lines += [f"- `{r['id']}` [{r['answer']}|{r['subject']}]"
                              f" {r['stem']}", f"  - 解析：{r['analysis']}",
                              f"  - 依据：{r['basis']}"]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"报告已写入 {args.report}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
