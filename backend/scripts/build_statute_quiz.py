"""从 data/法条库 生成客观题（法条驱动，origin='bank'，entry_id=NULL）。

定位：条目派生的题只覆盖「已经写进条目的考点」，而法条库补全后还有大量条文
（尤其新增法、司法解释、国际条约）没有进入训练闭环。本脚本按覆盖率缺口补题：

  候选 A：条目 statutes 引用过、但还没有任何题目覆盖的条文（按被引用条目数降序）
  候选 B：每部法按 --per-law 配额补足未覆盖条文（数字/要件型条文优先）

产物 basis 统一写成「<规范法名><条号>」（法条库文件主名经 statutes.display_law_name
换成展示法名，如「民营经济促进法-全文第四十一条」→「中华人民共和国民营经济促进法第四十一条」），
便于覆盖率统计、去重与法条页跳转。

用法：
    .venv/bin/python scripts/build_statute_quiz.py --dry-run
    .venv/bin/python scripts/build_statute_quiz.py --only-cited --limit 50 --workers 6
    .venv/bin/python scripts/build_statute_quiz.py --per-law 3 --workers 6
    .venv/bin/python scripts/build_statute_quiz.py --publish
"""
import argparse
import collections
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, db, number_terms, quiz_bank, statute_index, statutes  # noqa: E402
from scripts.build_judge_bank import _score_article, subject_of  # noqa: E402
from scripts.build_quiz_bank import MIN_ANALYSIS, MIN_OPTIONS, check_quiz  # noqa: E402

SYSTEM = ("你是法考客观题命题助手。依据现行法条原文命制案例化选择题，"
          "严格输出 JSON，不要任何解释文字。")

USER_TEMPLATE = """下面是一条现行法条原文。请据此命一道法考客观题（单选，四选一）。

要求：
1. stem：60—160 字的案例化题干，设计具体案情让考生判断法律后果，
   **不要照抄条文**，也不要点出答案；
2. options：4 个选项，正确项＝本条的结论，**必须用自己的话概括改写**（不得出现
   连续 12 字以上与条文原文相同的表述，也不要直接用条文原句）；其余 3 项为易混
   干扰（主体、期限、数额、程序、效力等常见混淆点）；
3. answer：单个字母 A/B/C/D；
4. analysis：40—80 字，说明依据条文与关键要件，并指出干扰项错在哪；
5. basis：填空串，保持原样输出 "{basis}"。

只输出如下 JSON：
{{"stem":"……","options":["A. ……","B. ……","C. ……","D. ……"],
  "answer":"A","analysis":"……","basis":"{basis}"}}

法条（{law}{label}）：
{text}
"""


def covered_map(conn) -> dict[str, set[tuple[int, int]]]:
    """已被**已发布**题目覆盖的条文：{法条库主名: {(条号, 子条号)}}。

    只算 published：draft 还在生成流程里（用户练不到），
    否则同一轮草稿会把下一轮的缺口算成 0。
    """
    out: dict[str, set[tuple[int, int]]] = {}
    for row in conn.execute(
            "SELECT basis FROM quizzes WHERE basis != '' AND status='published'"):
        located = statutes.resolve_law_article(row["basis"])
        if located:
            out.setdefault(located[0], set()).add((located[1], located[2]))
    return out


def cited_counter(conn) -> collections.Counter:
    """条目 statutes 引用计数：{(法条库主名, 条号, 子条号): 被引用条目数}。"""
    counter: collections.Counter = collections.Counter()
    for row in conn.execute(
            "SELECT statutes FROM v_entries WHERE status='final'"):
        for ref in json.loads(row["statutes"] or "[]"):
            located = statutes.resolve_law_article(ref)
            if located:
                counter[located] += 1
    return counter


def cited_candidates(conn) -> list[dict]:
    covered = covered_map(conn)
    out = []
    for (key, no, sub), cites in cited_counter(conn).most_common():
        if (no, sub) in covered.get(key, set()):
            continue
        out.append({"law": key, "no": no, "sub": sub, "cites": cites})
    return out


def quota_candidates(conn, per_law: int, laws: list[str] | None = None) -> list[dict]:
    """每部法补足配额：优先数字/要件型条文（评分高者在前）。"""
    covered = covered_map(conn)
    library = statute_index.load_library()
    out = []
    for key, law in library.items():
        if laws and not any(token in key for token in laws):
            continue
        missing = [a for a in law.articles
                   if (a.no, a.sub) not in covered.get(key, set())]
        missing.sort(key=lambda a: -_score_article(a.text))
        for article in missing[:per_law]:
            out.append({"law": key, "no": article.no, "sub": article.sub,
                        "cites": 0})
    return out


def target_candidates(conn, ratio: float,
                      laws: list[str] | None = None) -> list[dict]:
    """按目标覆盖率反推每部法的缺口条文（数字/要件型优先）。

    统一配额（`--per-law`）在大法典上追不上目标：民法典 1260 条、生态环境法典 1242 条、
    人民检察院刑事诉讼规则 684 条。这里按「需要 = ceil(ratio × 条数) − 已覆盖」
    逐法算缺口，小法不再重复占配额。
    """
    covered = covered_map(conn)
    out = []
    for key, law in statute_index.load_library().items():
        if laws and not any(token in key for token in laws):
            continue
        articles = {(a.no, a.sub): a for a in law.articles}
        have = covered.get(key, set()) & set(articles)
        need = math.ceil(ratio * len(articles)) - len(have)
        if need <= 0:
            continue
        missing = [a for pk, a in articles.items() if pk not in have]
        missing.sort(key=lambda a: -_score_article(a.text))
        for article in missing[:need]:
            out.append({"law": key, "no": article.no, "sub": article.sub,
                        "cites": 0})
    return out


def _article(key: str, no: int, sub: int):
    law = statute_index.load_library().get(key)
    return law.article(no, sub) if law else None


def statute_basis(law_key: str, article) -> str:
    """题目依据写法：「规范法名+条号」（可被 statutes.resolve_law_article 反向解析）。"""
    return f"{statutes.display_law_name(law_key)}{article.label}"


def check_statute_quiz(quiz: dict, article_text: str) -> list[str]:
    """结构校验 + 正确项与条文相关 + 题干不得照抄条文。"""
    errs = check_quiz(quiz, {"conclusion": article_text})
    options = quiz.get("options") or []
    if len(options) < MIN_OPTIONS:
        return errs
    answer = (quiz.get("answer") or "").upper()
    if answer and all(0 <= ord(ch) - 65 < len(options) for ch in answer):
        picked = options[ord(answer[0]) - 65]
        if not (number_terms.extract(picked) & number_terms.extract(article_text)):
            # 无数字重合时可以接受，但正确项不能是条文的逐字复制
            if len(picked) > 0 and picked.strip(" A-D.、") in article_text:
                errs.append("正确项直接照抄条文")
    stem = (quiz.get("stem") or "").strip()
    window = 24
    if len(stem) >= window:
        for i in range(len(stem) - window + 1):
            if stem[i:i + window] in article_text:
                errs.append("题干照抄条文")
                break
    if len(quiz.get("analysis") or "") < MIN_ANALYSIS:
        errs.append("解析过短")
    return errs


def build_one(item: dict) -> tuple[dict, dict | None, list[str]]:
    article = _article(item["law"], item["no"], item["sub"])
    if article is None:
        return item, None, ["条文不存在"]
    law_name = statutes.display_law_name(item["law"])
    basis = statute_basis(item["law"], article)
    user = USER_TEMPLATE.format(law=law_name, label=article.label,
                                text=article.text, basis=basis)
    raw = ai.call_llm(SYSTEM, user, temperature=0.5, max_tokens=700)
    quiz = _parse(raw)
    if quiz is None:
        return item, None, ["输出不可解析"]
    return item, quiz, check_statute_quiz(quiz, article.text)


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
    options = data.get("options") or []
    answer = (data.get("answer") or "").strip().upper()
    if not data.get("stem") or len(options) < 2 or not answer:
        return None
    if not all(0 <= ord(ch) - 65 < len(options) for ch in answer):
        return None
    return {"stem": data["stem"].strip(), "options": options,
            "answer": "".join(sorted(set(answer))),
            "analysis": (data.get("analysis") or "").strip(),
            "basis": (data.get("basis") or "").strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从法条库生成客观题")
    ap.add_argument("--per-law", type=int, default=3, help="每部法补题配额")
    ap.add_argument("--target-ratio", type=float, default=0.0,
                    help="按目标覆盖率反推每部法缺口（0=改用 --per-law 统一配额）")
    ap.add_argument("--laws", default=None,
                    help="只补这些法（按文件名子串匹配，逗号分隔）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only-cited", action="store_true",
                    help="只处理「条目引用过但无题覆盖」的条文")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    conn = db.connect()
    if args.publish:
        n = quiz_bank.set_status(conn, origins=(quiz_bank.ORIGIN_BANK,),
                                 status="published")
        print(f"已发布 {n} 题")
        conn.close()
        return 0

    cited = cited_candidates(conn)
    laws = [x.strip() for x in args.laws.split(",") if x.strip()] if args.laws else None
    if args.only_cited:
        quota = []
    elif args.target_ratio > 0:
        quota = target_candidates(conn, args.target_ratio, laws)
        print(f"目标覆盖率 {args.target_ratio:.0%}：每部法缺口合计 {len(quota)} 条")
    else:
        quota = quota_candidates(conn, args.per_law, laws)
    items = cited if args.only_cited else cited + quota
    # 去重（同一法条可能同时出现在 A/B 两类候选里）
    seen = set()
    deduped = []
    for it in items:
        key = (it["law"], it["no"], it["sub"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    items = deduped[:args.limit] if args.limit else deduped
    by_subject = collections.Counter(subject_of(it["law"]) or "其他" for it in items)
    print(f"候选 {len(items)} 条（其中条目引用过 {len(cited)} 条）；科目分布 {dict(by_subject)}")
    if args.dry_run:
        for it in items[:10]:
            print("  -", it["law"], it["no"], f"引用{it['cites']}")
        conn.close()
        return 0

    ok = fail = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (item, quiz, errs) in enumerate(pool.map(build_one, items), 1):
            if quiz is None or errs:
                fail += 1
                print(f"[{i}/{len(items)}] FAIL {item['law']}{item['no']}: {errs[:1]}")
                continue
            article = _article(item["law"], item["no"], item["sub"])
            quiz_bank.save_question(
                conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                entry_id=None, subject=subject_of(item["law"]) or "",
                point="", stem=quiz["stem"], options=quiz["options"],
                answer=quiz["answer"], analysis=quiz["analysis"],
                basis=statute_basis(item["law"], article), status="draft")
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
