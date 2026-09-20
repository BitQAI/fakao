"""从案例库长案情生成第 4 题「综合大案例」（民法＋民诉＋商法，8—13 小问）。

与微主观题的差别：一题多问、跨科、分值最高（55 分 / 70 分钟）。
程序类设问**必须基于本案自身的程序事实**（管辖、当事人、举证、上诉、再审、执行）；
本案没有程序素材时，宁可不编程序问题，改补实体争点。

用法：
    python scripts/build_composite_questions.py --dry-run --limit 1
    python scripts/build_composite_questions.py --limit 2
    python scripts/build_composite_questions.py --publish     # 抽检后发布
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, subjective_templates as stpl  # noqa: E402
from scripts.subjective_build import (  # noqa: E402
    clean_points, llm_json_checked, publish, save_question)

MAX_CASE_CHARS = 6000
MIN_STEM, MAX_STEM = 600, 2600
MIN_REFERENCE = 200

#: 第 4 题固定落在民法综合（民法＋民诉＋商法）
SUBJECT = "民法"
#: 候选筛选：民事 + 商法味的关键词（第 4 题常考公司/担保/合同/破产）
CIVIL_TERMS = ("合同", "公司", "股权", "担保", "破产", "保险", "票据",
               "买卖", "租赁", "建设工程", "借款", "抵押")

SYSTEM = ("你是法考主观题第 4 题（民法综合大案例）的命题助手。"
          "严格输出 JSON，不要任何解释文字。")

USER_TEMPLATE = """下面是一则真实民事/商事裁判案例。请把它改造成法考主观题第 4 题
（综合大案例：民法＋民诉＋商法），{min_q}—{max_q} 个小问。

要求：
1. stem：长案情，{min_s}—{max_s} 字（**不得超过 {max_s} 字**）。保留当事人（可用"甲""乙""A公司"代称）、
   关键时间、金额、行为与**程序经过**（是否起诉、有无反诉、审级）；
   不要出现法院名称、裁判结果与法院的说理。
2. questions：{min_q}—{max_q} 个设问，按「民法实体 4—6 问 → 民诉程序 2—3 问 →
   商法/其他 2—4 问」组织。
   - 实体问题必须围绕本案真实的争议焦点；
   - 程序问题（管辖、当事人适格、举证责任、上诉、再审、执行）**必须基于本案自身的
     程序事实**；本案程序素材不足就改补实体争点，**不要编造程序事实**；
   - 每一问自成一体，不依赖后面小问的答案；问句要具体到"谁对谁主张什么"。
3. points：{min_p}—{max_p} 个采分点（**总数不得超过 {max_p} 条**，平均每问 2 条，
   重点问最多 3 条；宁可少写也不要超）。
   - 每条必须带 qno（属于第几问，1—{max_q}）与 kind；
     kind 只能是 结论 / 依据 / 涵摄 / 抗辩 / 程序 / 救济；
   - **每一问至少 1 条采分点**，分值高的问（请求权基础、责任承担）可以 2—3 条；
   - 「依据」类必须写具体法条，填在 statutes（如「民法典第577条」「公司法第23条」）；
     如果这一问确实找不到对应条文，就把该条改成「涵摄」类，**不要交空的 statutes**；
     结论、涵摄、抗辩类可以不带法条。
4. reference：参考答案提纲，{min_ref} 字以上，逐问给结论与理由要点。

本科作答骨架（points 应覆盖其中关键步骤）：
{skeleton}

只输出如下 JSON：
{{"stem":"……","questions":["……"],
  "points":[{{"no":1,"qno":1,"kind":"结论","text":"……","statutes":[]}}],
  "reference":"……"}}

案例标题：{title}
案例正文：
{text}
"""


def candidates(conn, limit: int, min_chars: int = 2500) -> list:
    """长案情民事案例：含争议焦点、正文够长、带商法味关键词；优先最长与含公司/破产的。"""
    rows = conn.execute(
        "SELECT c.source, c.loc, c.title, c.keywords, c.text, LENGTH(c.text) AS n"
        " FROM cases c WHERE c.source='人民法院案例库' AND c.text LIKE '%争议焦点%'"
        " AND c.keywords LIKE '%\"民事\"%' AND LENGTH(c.text) >= ?"
        " AND NOT EXISTS (SELECT 1 FROM case_questions q"
        "   WHERE q.case_source=c.source AND q.case_loc=c.loc)"
        " ORDER BY n DESC", (min_chars,)).fetchall()
    out = []
    for row in rows:
        hay = f"{row['title'] or ''} {row['keywords'] or ''}"
        if not any(t in hay for t in CIVIL_TERMS):
            continue
        out.append(row)
    out.sort(key=lambda r: ("公司" in r["keywords"] or "破产" in r["keywords"], r["n"]),
             reverse=True)
    return out[:limit]


def validate(data: dict, relax: bool = True) -> tuple[dict | None, list[str]]:
    """校验综合大案例产物：小问区间、采分点数、qno 覆盖、依据类法条。"""
    if not isinstance(data, dict):
        return None, ["输出不是 JSON 对象"]
    spec = stpl.SPECS["composite"]
    problems: list[str] = []
    stem = (data.get("stem") or "").strip()
    questions = [str(q).strip() for q in (data.get("questions") or [])
                 if str(q).strip()]
    points = data.get("points") or []
    if not MIN_STEM <= len(stem) <= MAX_STEM:
        problems.append(f"案情长度 {len(stem)} 不在 {MIN_STEM}-{MAX_STEM}")
    if not spec["min_questions"] <= len(questions) <= spec["max_questions"]:
        problems.append(f"小问数 {len(questions)} 不在 "
                        f"{spec['min_questions']}-{spec['max_questions']}")
    if not spec["min_points"] <= len(points) <= spec["max_points"]:
        problems.append(f"采分点数 {len(points)} 不在 "
                        f"{spec['min_points']}-{spec['max_points']}")
    cleaned, point_problems = clean_points(
        points, stpl.POINT_KINDS, relax=relax,
        qno_max=len(questions) if questions else None)
    problems.extend(point_problems)
    bare = [i for i in range(1, len(questions) + 1)
            if not any(p.get("qno") == i for p in cleaned)]
    if bare and questions:
        problems.append(f"第 {'、'.join(map(str, bare))} 问没有采分点")
    reference = (data.get("reference") or "").strip()
    if len(reference) < MIN_REFERENCE:
        problems.append(f"参考提纲 {len(reference)} 字，少于 {MIN_REFERENCE}")
    if problems:
        return None, problems
    return {"stem": stem, "questions": questions, "points": cleaned,
            "reference": reference}, []


def build_one(row, relax: bool = True,
              attempts: int = 3) -> tuple[dict | None, list[str]]:
    spec = stpl.SPECS["composite"]
    user = USER_TEMPLATE.format(
        title=row["title"] or "", text=(row["text"] or "")[:MAX_CASE_CHARS],
        min_s=MIN_STEM, max_s=MAX_STEM, min_ref=MIN_REFERENCE,
        skeleton="\n".join(f"  - {s}" for s in stpl.COMPOSITE_SKELETON),
        min_q=spec["min_questions"], max_q=spec["max_questions"],
        min_p=spec["min_points"], max_p=spec["max_points"])
    return llm_json_checked(SYSTEM, user, lambda d: validate(d, relax=relax),
                            attempts=attempts, temperature=0.4, max_tokens=4200)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成第 4 题综合大案例")
    ap.add_argument("--limit", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-chars", type=int, default=2500, help="案例正文最短字数")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    conn = db.connect()
    try:
        if args.publish:
            print(f"已发布 {publish(conn, 'composite')} 道综合大案例")
            return 0
        todo = candidates(conn, args.limit, args.min_chars)
        print(f"候选案例 {len(todo)} 条")
        done = 0
        for i, row in enumerate(todo, 1):
            q, problems = build_one(row)
            if q is None:
                print(f"[{i}/{len(todo)}] {row['loc']} 丢弃：{problems[:3]}")
                continue
            if args.dry_run:
                print(f"[{i}/{len(todo)}] {row['loc']} OK（dry-run）"
                      f" 案情 {len(q['stem'])} 字 小问 {len(q['questions'])}"
                      f" 采分点 {len(q['points'])}")
            else:
                qid = save_question(
                    conn, case_source=row["source"], case_loc=row["loc"],
                    subject=SUBJECT, qtype="composite", stem=q["stem"],
                    questions=q["questions"], points=q["points"],
                    reference=q["reference"])
                print(f"[{i}/{len(todo)}] {row['loc']} 已入库 draft id={qid}"
                      f" 小问 {len(q['questions'])} 采分点 {len(q['points'])}")
            done += 1
        print(f"\n完成：成功 {done}/{len(todo)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
