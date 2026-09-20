"""生成「关系型判断题」题库（origin='judge', qtype='judge', variant=<词族>）。

与 `build_judge_bank.py`（数字判断题）并列：数字题考数量/金额/年限，关系题考
「可以/应当/必须/不得」「决定/决议」「一审/二审」「复议/复核」「独任/合议庭」这类
措辞与程序层级细节，错题只允许按 `app.relation_terms.SWAPS` 白名单偷换一处。

原料（与数字题一致）：
    --source statutes  从 data/法条库 抽取含关系词的条文（按词族，默认每条文最多 2 族）
    --source entries   从条目「场景 + 结论」出题
    --source counterparts  给只有「对」题的法条/条目补「错」题，配平答案分布

质量闸门：`app.relation_terms.check`（对题禁新增关系词、错题限白名单单点偷换、主体一致、
对题不得抄原文）；题干含数字时追加 `app.number_terms.is_grounded` 复核。

用法：
    .venv/bin/python scripts/build_relation_judge.py --source statutes --dry-run
    .venv/bin/python scripts/build_relation_judge.py --source statutes --max-per-article 2 --workers 8
    .venv/bin/python scripts/build_relation_judge.py --source entries --limit 50
    .venv/bin/python scripts/build_relation_judge.py --source counterparts --polarity false
    .venv/bin/python scripts/build_relation_judge.py --publish
"""
import argparse
import json
import re
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (ai, config, db, number_terms, quiz_bank, relation_terms,  # noqa: E402
                 statute_index, statutes)
from scripts.build_judge_bank import (article_blocks, canonical_basis,  # noqa: E402
                                     subject_of)

SYSTEM = "你是法考客观题教练，正在为考生出「关系型判断题」（只判断对错，不设选项）。"
POLARITY_HINT = {
    "auto": "",
    "true": "**本题必须是一句正确的陈述**（答案「对」）：措辞与原文完全一致。\n",
    "false": "**本题必须是一句错误的陈述**（答案「错」）：只偷换一处关系词。\n",
}
ORIGIN = quiz_bank.ORIGIN_JUDGE
#: 科目权重（180 分口径）：高权重科先出题，三国法这类低频科放最后
SUBJECT_PRIORITY = ("商经知劳环", "理论法", "民法", "刑法", "刑诉", "民诉", "行政法",
                    "三国法")


def covered_relations(conn, variant: str | None = None) -> set[tuple[str, int, str]]:
    """已出过题的法条 {(法条库主名, 条号, 词族)}，用于断点续跑。"""
    # archived（下架/回源不通过）不算已覆盖：让重跑能把它们补回来
    sql = ("SELECT basis, variant FROM quizzes WHERE origin=? AND basis != ''"
           " AND status != 'archived'")
    params: list = [ORIGIN]
    if variant:
        sql += " AND variant=?"
        params.append(variant)
    out: set[tuple[str, int, str]] = set()
    for row in conn.execute(sql, params).fetchall():
        located = statutes.resolve_law_article(row["basis"])
        if located:
            out.add((located[0], located[1], row["variant"]))
    return out


def covered_entries(conn, variant: str | None = None) -> set[tuple[str, str]]:
    sql = ("SELECT entry_id, variant FROM quizzes WHERE origin=? AND entry_id IS NOT NULL"
           " AND status != 'archived'")
    params: list = [ORIGIN]
    if variant:
        sql += " AND variant=?"
        params.append(variant)
    return {(r["entry_id"], r["variant"]) for r in conn.execute(sql, params).fetchall()}


def statute_candidates(conn, *, max_per_article: int = 2,
                       laws: list[str] | None = None,
                       families: list[str] | None = None) -> list[dict]:
    """扫描法条库：每个含关系词的条文按稀有度取 ≤max_per_article 个词族出题。"""
    covered = covered_relations(conn)
    out: list[dict] = []
    for path in sorted(config.STATUTE_DIR.glob("*.md")):
        law = path.stem
        if laws and law not in laws:
            continue
        subject = subject_of(law)
        if subject is None:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for no, body in article_blocks(text):
            hits = relation_terms.families_of(body)
            if families:
                hits = [f for f in hits if f in families]
            picked = hits if max_per_article <= 0 else hits[:max_per_article]
            for family in picked:
                # article_blocks 的条号是 int；covered 的键用「法条库主名 + 条号」
                # （resolve_law_article 返回的 law_key 就是法条库文件主名）
                if (law, no, family) in covered:
                    continue
                out.append({"law": law, "no": no, "subject": subject,
                            "family": family, "text": body})
    # 稳定排序：同一科目内仍保持「法名 + 条文顺序」
    out.sort(key=lambda it: SUBJECT_PRIORITY.index(it["subject"])
             if it["subject"] in SUBJECT_PRIORITY else len(SUBJECT_PRIORITY))
    return out


def entry_candidates(conn, *, limit: int = 0,
                     families: list[str] | None = None) -> list[dict]:
    covered = covered_entries(conn)
    rows = conn.execute(
        "SELECT id, subject, point, anchor, conclusion, statutes FROM v_entries"
        " WHERE status='final'").fetchall()
    out: list[dict] = []
    for r in rows:
        text = f"{r['anchor']}。{r['conclusion']}"
        hits = relation_terms.families_of(text)
        if families:
            hits = [f for f in hits if f in families]
        if not hits:
            continue
        family = hits[0]
        if (r["id"], family) in covered:
            continue
        out.append({"entry_id": r["id"], "subject": r["subject"],
                    "point": r["point"], "anchor": r["anchor"],
                    "conclusion": r["conclusion"], "family": family,
                    "statutes": json.loads(r["statutes"] or "[]")})
    return out[:limit] if limit else out


def counterpart_candidates(conn, *, limit: int = 0,
                           families: list[str] | None = None) -> list[dict]:
    """已有「对」题、缺「错」题的法条/条目 → 补错题（与数字题同一配对思路）。"""
    rows = conn.execute(
        "SELECT basis, entry_id, answer, variant FROM quizzes"
        " WHERE origin=? AND status != 'archived' AND variant NOT IN ('', 'number')",
        (ORIGIN,)).fetchall()      # 只给关系题配对：数字题由 build_judge_bank 负责
    true_statute = {(r["basis"], r["variant"]) for r in rows
                    if r["answer"] == "对" and not r["entry_id"] and r["basis"]}
    false_statute = {(r["basis"], r["variant"]) for r in rows
                     if r["answer"] == "错" and not r["entry_id"]}
    true_entry = {(r["entry_id"], r["variant"]) for r in rows
                  if r["answer"] == "对" and r["entry_id"]}
    false_entry = {(r["entry_id"], r["variant"]) for r in rows
                   if r["answer"] == "错" and r["entry_id"]}
    library = statute_index.load_library()
    out: list[dict] = []
    for basis, variant in sorted(true_statute - false_statute):
        if families and variant not in families:
            continue
        located = statutes.resolve_law_article(basis)
        if located is None:
            continue
        law_key, no, sub = located
        law = library.get(law_key)
        article = law.article(no, sub) if law else None
        if article is None:
            continue
        # 该条文里没有可偷换的词（多为「文件第X条 ≠ 法条库第X条」的错位）→ 不出题
        if _pick_swap(relation_terms.terms_of(article.text), basis) is None:
            continue
        out.append({"law": law_key, "no": f"第{no}条", "sub": sub,
                    "text": article.text, "family": variant,
                    "subject": subject_of(law_key) or "", "polarity": "false"})
    for entry_id, variant in sorted(true_entry - false_entry):
        if families and variant not in families:
            continue
        row = conn.execute(
            "SELECT id, subject, point, anchor, conclusion, statutes FROM v_entries"
            " WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            continue
        text = f"{row['anchor']}。{row['conclusion']}"
        if _pick_swap(relation_terms.terms_of(text), entry_id) is None:
            continue
        out.append({"entry_id": row["id"], "subject": row["subject"],
                    "point": row["point"], "anchor": row["anchor"],
                    "conclusion": row["conclusion"], "family": variant,
                    "statutes": json.loads(row["statutes"] or "[]"),
                    "polarity": "false"})
    return out[:limit] if limit else out


def _pick_swap(allowed: set[str], key: str) -> tuple[str, str] | None:
    """从原文命中的关系词里挑一个「允许被偷换」的定向替换（按 key 稳定轮换）。

    交给模型自己挑时，错题通过率只有 7%~18%；直接指定要改的那一处能显著提高命中率。
    """
    pairs = [(term, target) for term in sorted(allowed)
             for target in relation_terms.swaps_for(term)]
    if not pairs:
        return None
    return pairs[zlib.crc32(key.encode("utf-8")) % len(pairs)]


def _sentence_with(text: str, term: str) -> str:
    """取含某关系词的最短单句：让「照抄 + 只改一处」有明确边界，避免截断长条文。"""
    sentences = [s.strip() for s in re.split(r"[。；\n]", text or "") if s.strip()]
    hits = [s for s in sentences if term in s]
    return min(hits, key=len) if hits else (text or "")


def relation_prompt(reference: str, hint: str, family: str,
                    polarity: str = "auto",
                    allowed_terms: set[str] | None = None,
                    forced_swap: tuple[str, str] | None = None) -> str:
    """出题提示词：把「原文允许出现的关系词」与「允许的偷换」写死给模型，
    否则模型很容易自造关系词（实测闸门通过率仅 28%）。"""
    terms = relation_terms.FAMILIES[family]
    swaps = [(term, targets) for term, targets in relation_terms.SWAPS.items()
             if term in terms]
    swap_text = "；".join(f"{t}→{'/'.join(targets)}" for t, targets in swaps)
    allowed_text = ""
    if allowed_terms:
        allowed_text = ("- 题干里**只能**出现这些关系词：" + "、".join(
            sorted(allowed_terms, key=len, reverse=True)) + "\n")
    swap_allowed = sorted({f"{t}→{w}" for t in (allowed_terms or ())
                           for w in relation_terms.swaps_for(t)})
    swap_allowed_text = ""
    if forced_swap:
        swap_allowed_text = (
            f"- **逐字照抄下面这段原文，只把「{forced_swap[0]}」改成「{forced_swap[1]}」**；"
            "其余一字不改（不换同义词、不改语序、不增删任何内容），answer 必须是「错」\n")
    elif swap_allowed:
        swap_allowed_text = ("- 出「错」题时只允许从这些偷换里挑一个："
                             + "；".join(swap_allowed[:12]) + "\n")
    rules = (
        f"- 只考一个考点：本条文里的「{family}」类措辞（{'、'.join(terms)}）\n"
        "- stem：一句话陈述句，15~40 字，直接给出「谁可以/应当做什么、走哪道程序」的结论\n"
        "- answer：\"对\" 或 \"错\"\n"
        + allowed_text + swap_allowed_text +
        f"- 出「错」题时只允许偷换一处，且必须在白名单内：{swap_text or '不得偷换'}\n"
        "- 不得改动机关主体、期限与其他数字；不得整句照抄原文\n"
        "- analysis：30~60 字，点明依据里的正确措辞\n"
        "- basis：法名+条号（如「刑诉法第91条」），没有则空串\n"
        "只输出 JSON：{\"stem\":\"...\",\"answer\":\"对\",\"analysis\":\"...\","
        "\"basis\":\"...\"}\n\n依据原文：\n"
    )
    head = ("下面是一段法考依据原文。请据此出一道「关系型判断题」，只考措辞与程序层级"
            "（可以/应当、决定/决议、一审/二审、复议/复核、独任/合议庭 之类）的细节。"
            "约束：\n" + POLARITY_HINT.get(polarity, ""))
    return head + rules + reference + ("\n\n参考条目：" + hint if hint else "")


def _parse(raw: str | None) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return None
    stem = (data.get("stem") or "").strip()
    answer = (data.get("answer") or "").strip()
    if answer not in ("对", "错") or not 10 <= len(stem) <= 60:
        return None
    return {"stem": stem, "answer": answer,
            "analysis": (data.get("analysis") or "").strip(),
            "basis": (data.get("basis") or "").strip()}


def build_one(item: dict, polarity: str = "auto") -> tuple[dict, dict | None, str]:
    if item["family"] not in relation_terms.FAMILIES:
        return item, None, f"未知词族 {item['family']}"
    reference = item.get("text") or f"{item['anchor']}。{item['conclusion']}"
    allowed = relation_terms.terms_of(reference)
    answer_hint = item.get("polarity", polarity)
    forced = None
    if answer_hint == "false":
        key = item.get("basis") or item.get("entry_id") or reference
        forced = _pick_swap(allowed, str(key))
        if forced:
            # 把「依据原文」收缩到含该词的那一句：照抄范围明确，闸门也按同一段比对
            reference = _sentence_with(reference, forced[0]) + "。"
    hint = ""
    if item.get("entry_id"):
        hint = f"{item['point']}（场景：{item['anchor']}）"
        if item.get("statutes"):
            hint += "；关联法条：" + "、".join(item["statutes"][:2])
    raw = ai.call_llm(
        SYSTEM,
        relation_prompt(reference, hint, item["family"],
                        answer_hint, allowed_terms=allowed, forced_swap=forced),
        temperature=0.5, max_tokens=300)
    quiz = _parse(raw)
    if quiz is None:
        return item, None, "输出不可解析"
    ok, why = relation_terms.check(quiz["stem"], reference, quiz["answer"])
    if not ok:
        return item, quiz, why
    if number_terms.extract(quiz["stem"]):          # 关系题里出现数字 → 数字也要可核验
        fabricated = number_terms.fabricated(quiz["stem"], reference)
        if fabricated:
            return item, quiz, f"题干含原文外的数字 {sorted(fabricated)}"
    return item, quiz, ""


def _basis_of(item: dict, quiz: dict) -> str:
    """法条侧统一用「规范法名+条号」，便于去重、统计与前端跳转。"""
    if not item.get("law"):
        return quiz["basis"]
    return canonical_basis(f"{item['law']}{item['no']}") or quiz["basis"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成关系型判断题题库")
    ap.add_argument("--source", choices=["statutes", "entries", "both", "counterparts"],
                    default="statutes")
    ap.add_argument("--polarity", choices=["auto", "true", "false"], default="auto")
    ap.add_argument("--max-per-article", type=int, default=2,
                    help="每个条文最多取几个词族出题（0=全展开）")
    ap.add_argument("--law", action="append", default=[],
                    help="只跑指定法（法条库文件名，可重复）")
    ap.add_argument("--family", action="append", default=[],
                    help="只跑指定词族（可重复，默认全部 17 族）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    conn = db.connect()
    if args.publish:
        n = quiz_bank.set_status(conn, origins=(ORIGIN,), status="published")
        print(f"已发布 {n} 题（origin=judge，archived 不参与）")
        conn.close()
        return 0

    families = args.family or None
    items: list[dict] = []
    if args.source in ("statutes", "both"):
        picked = statute_candidates(conn, max_per_article=args.max_per_article,
                                    laws=args.law or None, families=families)
        print(f"法条候选 {len(picked)} 条")
        items += picked
    if args.source in ("entries", "both"):
        picked = entry_candidates(conn, limit=args.limit, families=families)
        print(f"条目候选 {len(picked)} 条")
        items += picked
    if args.source == "counterparts":
        picked = counterpart_candidates(conn, limit=args.limit, families=families)
        print(f"配对补「错」题候选 {len(picked)} 条")
        items += picked
    if args.limit:
        items = items[:args.limit]
    if args.dry_run:
        by_family: dict[str, int] = {}
        by_subject: dict[str, int] = {}
        for it in items:
            by_family[it["family"]] = by_family.get(it["family"], 0) + 1
            by_subject[it["subject"]] = by_subject.get(it["subject"], 0) + 1
        print("词族分布:", dict(sorted(by_family.items(), key=lambda kv: -kv[1])))
        print("科目分布:", dict(sorted(by_subject.items(), key=lambda kv: -kv[1])))
        conn.close()
        return 0

    ok = fail = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (item, quiz, why) in enumerate(
                pool.map(lambda it: build_one(it, args.polarity), items), 1):
            if quiz is None or why:
                fail += 1
                print(f"[{i}/{len(items)}] FAIL {why} | "
                      f"{(quiz or {}).get('stem', '')[:40]}")
                continue
            try:
                quiz_bank.save_question(
                    conn, qtype="judge", origin=ORIGIN, entry_id=item.get("entry_id"),
                    subject=item["subject"], point=item.get("point", ""),
                    stem=quiz["stem"], options=[], answer=quiz["answer"],
                    analysis=quiz["analysis"], basis=_basis_of(item, quiz),
                    variant=item["family"], status="draft")
            except Exception as exc:  # noqa: BLE001 - 单题写库失败不中断整批
                fail += 1
                print(f"[{i}/{len(items)}] FAIL 入库异常 {exc} |"
                      f" {quiz['stem'][:40]}")
                continue
            ok += 1
            if i % 25 == 0 or i == len(items):
                print(f"[{i}/{len(items)}] ok={ok} fail={fail} "
                      f"{time.time() - start:.0f}s")
    print(f"完成：入库 {ok}，丢弃 {fail}；未发布（加 --publish 发布）")
    print("题库概览:", json.dumps(quiz_bank.stats(conn), ensure_ascii=False))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
