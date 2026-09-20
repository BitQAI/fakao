"""用已入库条目批量生成客观题题库（origin='bank'，默认 draft）。

用法：
    .venv/bin/python scripts/build_quiz_bank.py --dry-run
    .venv/bin/python scripts/build_quiz_bank.py --subject 民法 --limit 20
    .venv/bin/python scripts/build_quiz_bank.py --only-missing --workers 6
    .venv/bin/python scripts/build_quiz_bank.py --publish            # draft → published

入库后由 quiz_service 优先抽题（题库缺题才回退 LLM 现生成）。
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, db, quiz_bank  # noqa: E402

MIN_OPTIONS = 4
MIN_ANALYSIS = 10


def entries_to_process(conn, subject: str | None, priority: str | None,
                       only_missing: bool, limit: int) -> list[dict]:
    sql = ("SELECT id, subject, submodule, point, anchor, conclusion, note, statutes,"
           " priority FROM entries WHERE status='final'")
    params: list = []
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if priority:
        sql += " AND priority=?"
        params.append(priority)
    if only_missing:
        sql += (" AND id NOT IN (SELECT entry_id FROM quizzes WHERE origin=?"
                " AND entry_id IS NOT NULL)")
        params.append(quiz_bank.ORIGIN_BANK)
    # 高频/易错/新增优先，普通考点排后
    sql += (" ORDER BY CASE priority WHEN '高频考点' THEN 0 WHEN '易错陷阱' THEN 1"
            " WHEN '新增必考' THEN 2 ELSE 3 END, id")
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    return rows[:limit] if limit else rows


def peers_for(conn, entry: dict) -> list[dict]:
    """同 submodule 的其他条目（供设计干扰项）。"""
    rows = conn.execute(
        "SELECT point, conclusion FROM entries WHERE status='final'"
        " AND subject=? AND submodule=? AND id!=? LIMIT 6",
        (entry["subject"], entry["submodule"], entry["id"])).fetchall()
    return [dict(r) for r in rows]


def check_quiz(quiz: dict, entry: dict) -> list[str]:
    """客观题硬校验：选项数、答案合法性、解析长度、正确项须与结论相关。"""
    errs: list[str] = []
    options = quiz.get("options") or []
    if len(options) < MIN_OPTIONS:
        errs.append(f"选项不足 {MIN_OPTIONS}")
    if len({o.strip() for o in options}) != len(options):
        errs.append("存在重复选项")
    answer = (quiz.get("answer") or "").upper()
    if not answer or not all(0 <= ord(ch) - 65 < len(options) for ch in answer):
        errs.append(f"答案非法: {answer!r}")
    if len(quiz.get("analysis") or "") < MIN_ANALYSIS:
        errs.append("解析过短")
    if len((quiz.get("stem") or "").strip()) < 8:
        errs.append("题干过短")
    conclusion = entry.get("conclusion") or ""
    if answer and not errs:
        picked = [options[ord(ch) - 65] for ch in answer
                  if 0 <= ord(ch) - 65 < len(options)]
        # 多选题的正确项会拆分结论句，因此只要有任一项与结论对得上即可
        if not any(_overlap(text, conclusion) or _same_numbers(text, conclusion)
                   or _similar(text, conclusion)
                   for text in picked):
            errs.append("正确项与条目结论无明显对应")
    return errs


def _overlap(text: str, conclusion: str, n: int = 4) -> bool:
    """正确项与结论应有 ≥n 字的公共子串（防答案张冠李戴）。"""
    clean = lambda s: "".join(ch for ch in s if ch.isalnum())  # noqa: E731
    a, b = clean(text), clean(conclusion)
    if len(a) < n or len(b) < n:
        return bool(set(a) & set(b))
    return any(a[i:i + n] in b for i in range(len(a) - n + 1))


def _same_numbers(text: str, conclusion: str) -> bool:
    """正确项与结论含同一数字表达（数字型考点最常见的对应方式）。"""
    from app import number_terms

    bare = lambda s: {(v, u) for v, u, _b in number_terms.extract(s)}  # noqa: E731
    return bool(bare(text) & bare(conclusion))


def _similar(text: str, conclusion: str, threshold: float = 0.15) -> bool:
    """二元组重合度兜底：正确项常是结论的压缩或同义改写（如「1倍以上5倍以下」）。"""
    clean = lambda s: "".join(ch for ch in s if ch.isalnum())  # noqa: E731
    a, b = clean(text), clean(conclusion)
    if len(a) < 4 or len(b) < 4:
        return bool(set(a) & set(b))
    grams_a = {a[i:i + 2] for i in range(len(a) - 1)}
    grams_b = {b[i:i + 2] for i in range(len(b) - 1)}
    return len(grams_a & grams_b) / max(1, min(len(grams_a), len(grams_b))) >= threshold


def build_one(entry: dict, peers: list[dict]) -> tuple[dict, dict | None, list[str]]:
    """单条出题（线程内执行，不碰数据库）。"""
    quiz = ai.generate_quiz(entry, peers=peers)
    if not quiz:
        return entry, None, ["LLM 无输出"]
    return entry, quiz, check_quiz(quiz, entry)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批量生成客观题题库")
    ap.add_argument("--subject", default=None)
    ap.add_argument("--priority", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only-missing", action="store_true",
                    help="跳过已有题库题的条目（断点续跑）")
    ap.add_argument("--publish", action="store_true",
                    help="把库内 draft 题转 published（不生成新题）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    conn = db.connect()
    if args.publish:
        n = quiz_bank.set_status(conn, origins=(quiz_bank.ORIGIN_BANK,),
                                 status="published",
                                 subjects=[args.subject] if args.subject else None)
        print(f"已发布 {n} 题（origin=bank）")
        conn.close()
        return 0

    rows = entries_to_process(conn, args.subject, args.priority,
                              args.only_missing, args.limit)
    print(f"待出题 {len(rows)} 条"
          + (f"（科目 {args.subject}）" if args.subject else ""))
    if args.dry_run:
        by_sub: dict[str, int] = {}
        for r in rows:
            by_sub[r["subject"]] = by_sub.get(r["subject"], 0) + 1
        print("科目分布:", by_sub)
        conn.close()
        return 0

    tasks = [(r, peers_for(conn, r)) for r in rows]
    ok = fail = skip = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (entry, quiz, errs) in enumerate(
                pool.map(lambda t: build_one(*t), tasks), 1):
            if errs or quiz is None:
                fail += 1
                print(f"[{i}/{len(tasks)}] FAIL {entry['id']} {entry['point']}:"
                      f" {errs[:1]}")
                continue
            qid = quiz_bank.save_question(
                conn, qtype="choice", origin=quiz_bank.ORIGIN_BANK,
                entry_id=entry["id"], subject=entry["subject"],
                point=entry["point"], stem=quiz["stem"], options=quiz["options"],
                answer=quiz["answer"], analysis=quiz["analysis"],
                basis=quiz.get("basis", ""), status="draft")
            if qid is None:
                skip += 1
            else:
                ok += 1
            if i % 20 == 0 or i == len(tasks):
                print(f"[{i}/{len(tasks)}] ok={ok} fail={fail} "
                      f"{time.time() - start:.0f}s")
    print(f"完成：入库 {ok}，失败 {fail}，跳过 {skip}；未发布（加 --publish 发布）")
    print("题库概览:", json.dumps(quiz_bank.stats(conn), ensure_ascii=False))
    conn.close()
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
