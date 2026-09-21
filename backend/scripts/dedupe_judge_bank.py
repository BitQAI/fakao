"""判断题去重 / 降相似：把重复与高度相似的题归档（`status='archived'`，可逆）。

四条规则（按序执行，每组只留信息量最大的一题：解析更长者优先，其次有依据者优先）：
  R1 完全重复   —— 题干 + 答案完全相同
  R2 同源近似   —— 同 basis + 同词族 + 同答案，题干相似度 ≥ 0.75
  R3 同法模板化 —— 同一部法内、把数字抹成 # 后题干完全相同
  R4 同源超额   —— 同 basis + 同词族 + 同答案超过 1 题（「对/错」配对是允许的）

R3 只收缩同一部法内的模板句（如某公约反复出现的签署/生效句式）；不同法但同句式的题
（两部公约各自的签字截止日）属不同考点，保留。

R2/R4 的分组键带 `variant`：同一条文可以出多个词族的题（如既考「独任/合议庭」又考
「复议/复核」），不带 variant 会把不同考点的题误归档；数字题（variant=number）行为不变。

归档不删除：行与 `quiz_answers` 历史答题记录都保留，改回 published 即恢复；
`quiz_bank.set_status`（`--publish`）不会复活归档题。

用法：
    .venv/bin/python scripts/dedupe_judge_bank.py                      # dry-run
    .venv/bin/python scripts/dedupe_judge_bank.py --apply
    .venv/bin/python scripts/dedupe_judge_bank.py --report ../docs/superpowers/research/2026-09-20-数字判断题去重报告.md
"""
import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, quiz_bank  # noqa: E402

SIMILARITY_THRESHOLD = 0.75
_DIGIT_RE = re.compile(r"[0-9〇零一二三四五六七八九十百千万]+")
_ARTICLE_NO_RE = re.compile(r"第[〇零一二三四五六七八九十百千万0-9]+条.*$")


def _rank(row) -> tuple[int, int, int]:
    """保留优先级：解析更长 → 有依据 → id 更小。"""
    return (-len(row["analysis"] or ""), 0 if row["basis"] else 1, row["id"])


def _law_of(basis: str) -> str:
    return _ARTICLE_NO_RE.sub("", basis or "").strip()


def _masked(stem: str) -> str:
    return _DIGIT_RE.sub("#", stem or "")


def _load(conn, origin: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, entry_id, basis, subject, stem, answer, analysis, variant"
        " FROM quizzes WHERE origin=? AND status != 'archived'", (origin,)).fetchall()
    return [dict(r) for r in rows]


def _apply_rule(rule: str, groups: dict, archived: dict) -> None:
    """组内保留最优题，其余登记归档。"""
    for rows in groups.values():
        if len(rows) < 2:
            continue
        rows = sorted(rows, key=_rank)
        keep = rows[0]
        for row in rows[1:]:
            if row["id"] in archived:
                continue
            archived[row["id"]] = {"rule": rule, "keep_id": keep["id"],
                                   "keep_stem": keep["stem"]}


def plan(conn, *, origin: str = quiz_bank.ORIGIN_JUDGE) -> list[dict]:
    """返回 [{id, rule, keep_id, stem}]：本次应归档的题。"""
    rows = _load(conn, origin)
    archived: dict[int, dict] = {}

    # R1 完全重复
    groups: dict = {}
    for r in rows:
        groups.setdefault((r["stem"], r["answer"]), []).append(r)
    _apply_rule("R1_完全重复", groups, archived)

    alive = [r for r in rows if r["id"] not in archived]

    # R2 同源近似（同 basis + 同词族 + 同答案）
    groups = {}
    for r in alive:
        groups.setdefault((r["basis"], r["variant"], r["answer"]), []).append(r)
    for key, rs in groups.items():
        if len(rs) < 2:
            continue
        keep: list[dict] = []
        for r in sorted(rs, key=_rank):
            if any(SequenceMatcher(None, r["stem"], o["stem"]).ratio()
                   >= SIMILARITY_THRESHOLD for o in keep):
                archived[r["id"]] = {"rule": "R2_同源近似",
                                     "keep_id": keep[0]["id"], "keep_stem": keep[0]["stem"]}
            else:
                keep.append(r)

    # R3 同法模板化（数字抹平后完全同句）；答案参与分组，避免吃掉「对/错」配对
    groups = {}
    for r in rows:
        if r["id"] in archived:
            continue
        groups.setdefault(
            (_law_of(r["basis"]), _masked(r["stem"]), r["answer"]), []).append(r)
    _apply_rule("R3_同法模板化", groups, archived)

    # R4 同源超额（同 basis + 同词族 + 同答案 > 1）
    groups = {}
    for r in rows:
        if r["id"] in archived:
            continue
        groups.setdefault((r["basis"], r["variant"], r["answer"]), []).append(r)
    _apply_rule("R4_同源超额", groups, archived)

    by_id = {r["id"]: r for r in rows}
    return [{"id": qid, "rule": info["rule"], "keep_id": info["keep_id"],
             "keep_stem": info["keep_stem"], "stem": by_id[qid]["stem"],
             "basis": by_id[qid]["basis"], "variant": by_id[qid]["variant"],
             "answer": by_id[qid]["answer"]} for qid, info in sorted(archived.items())]


def apply(conn, items: list[dict]) -> int:
    """把待归档题置为 archived（可逆）。"""
    for item in items:
        conn.execute("UPDATE quizzes SET status='archived' WHERE id=?", (item["id"],))
    conn.commit()
    return len(items)


def _write_report(path: Path, origin: str, items: list[dict], before: dict) -> None:
    counts: dict[str, int] = {}
    for item in items:
        counts[item["rule"]] = counts.get(item["rule"], 0) + 1
    lines = [f"# 判断题去重报告（origin={origin}）", "",
             f"- 去重前：{before['total']} 题（published {before['published']} /"
             f" draft {before['draft']} / archived {before['archived']}）",
             f"- 本次归档：{len(items)} 题",
             f"- 规则分布：{json.dumps(counts, ensure_ascii=False)}", "",
             "| id | 规则 | 答案 | 题干 | 保留 id |", "|---|---|---|---|---|"]
    lines += [f"| {i['id']} | {i['rule']} | {i['answer']} | {i['stem'][:40]} |"
              f" {i['keep_id']} |" for i in items]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _snapshot(conn, origin: str) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) n FROM quizzes WHERE origin=? GROUP BY status",
        (origin,)).fetchall()
    counts = {r["status"]: r["n"] for r in rows}
    return {"total": sum(counts.values()), "published": counts.get("published", 0),
            "draft": counts.get("draft", 0), "archived": counts.get("archived", 0)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="判断题去重/降相似（归档）")
    ap.add_argument("--origin", default=quiz_bank.ORIGIN_JUDGE)
    ap.add_argument("--apply", action="store_true", help="真正归档（默认只 dry-run）")
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args(argv)

    conn = db.connect()
    before = _snapshot(conn, args.origin)
    items = plan(conn, origin=args.origin)
    print(f"origin={args.origin} 去重前 {before}；待归档 {len(items)} 题")
    counts: dict[str, int] = {}
    for item in items:
        counts[item["rule"]] = counts.get(item["rule"], 0) + 1
    print("规则分布:", json.dumps(counts, ensure_ascii=False))
    for item in items[:10]:
        print(f"  [{item['rule']}] {item['id']} → 保留 {item['keep_id']} |"
              f" {item['stem'][:34]}")
    if args.report:
        _write_report(args.report, args.origin, items, before)
        print(f"报告已写入 {args.report}")
    if not args.apply:
        print("dry-run：未写库（加 --apply 归档）")
        conn.close()
        return 0
    n = apply(conn, items)
    print(f"已归档 {n} 题；现状 {_snapshot(conn, args.origin)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
