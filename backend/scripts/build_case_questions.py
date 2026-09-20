"""从案例库生成「每日案例」微主观题（题干 + 设问 + 采分点 + 参考答案）。

候选池：人民法院案例库中含明确「争议焦点」段的案例（约 1752 条）。
LLM 只做「压缩案情 + 抽采分点」，采分点必须在裁判理由里有依据，可回溯核对。

用法：
    python scripts/build_case_questions.py --dry-run --limit 3
    python scripts/build_case_questions.py --subject 刑法 --limit 5
    python scripts/build_case_questions.py --publish        # 抽检后批量发布
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, db, subjective_templates as stpl  # noqa: E402
from scripts.subjective_build import (  # noqa: E402
    clean_points, extract_json, publish, save_question)

MAX_CASE_CHARS = 3500
MIN_STEM, MAX_STEM = 80, 400

SYSTEM = ("你是法考主观题命题助手。把真实裁判案例改造成一道可以练习的案例分析题，"
          "严格输出 JSON，不要任何解释文字。")

USER_TEMPLATE = """下面是一则真实裁判案例。请把它改造成一道法考主观题（案例分析）。

要求：
1. stem：压缩后的案情，120-350 字，保留人名、关键事实、争议数字，不要出现法院名称与判决结果；
2. questions：2-3 个设问，每个设问对应一个独立的法律问题；
3. points：5-7 个采分点，必须来自本案裁判理由。**每个采分点必须带 kind**，
   取值只能是 结论 / 依据 / 涵摄 / 抗辩 / 程序 / 救济，本科侧重：{kind_hint}。
   - 结论：定性或请求是否成立
   - 依据：法条或请求权基础（statutes 填这里，格式如「民法典第577条」）
   - 涵摄：本案事实如何对应到构成要件
   - 抗辩：对方抗辩是否成立
   - 程序 / 救济：程序是否合法、如何救济
   **不要只给结论**——真实考试里只写结论基本不得分；
4. reference：参考答案，200 字以内，按「结论 + 依据 + 涵摄」组织；
5. subject：从 刑法/民法/刑诉/民诉/商经知劳环/行政法 中选一个。

本科建议作答骨架（points 应覆盖其中关键步骤）：
{skeleton}

只输出如下 JSON：
{{"subject":"民法","stem":"……","questions":["……","……"],
  "points":[{{"no":1,"kind":"结论","text":"……","statutes":[]}},
            {{"no":2,"kind":"依据","text":"……","statutes":["民法典第577条"]}}],
  "reference":"……"}}

案例标题：{title}
案例正文：
{text}
"""


_SUBJECT_RULES = (
    ("刑诉", ("刑事诉讼", "管辖", "证据", "侦查", "审查起诉", "辩护", "庭审", "上诉")),
    ("刑法", ("刑事", "犯罪", "罪", "量刑")),
    ("行政法", ("行政", "处罚", "许可", "复议", "政府信息公开")),
    ("商经知劳环", ("公司", "破产", "票据", "保险", "证券", "劳动", "商标", "专利",
                "著作权", "知识产权", "竞争", "消费者", "环境")),
    ("民诉", ("民事诉讼", "执行异议", "仲裁", "调解")),
    ("民法", ("民事", "合同", "物权", "侵权", "婚姻", "继承", "担保")),
)


def classify(row) -> str | None:
    """按关键词把案例归到考纲科目；归不了返回 None（放弃该案例）。"""
    raw = row["keywords"]
    kw = json.loads(raw or "[]") if isinstance(raw, str) else (raw or [])
    hay = " ".join([row["title"] or "", row["category"] or "", *kw])
    for subject, terms in _SUBJECT_RULES:
        if subject == "刑法" and any(t in hay for t in ("民事", "行政", "合同")):
            continue
        if any(t in hay for t in terms):
            return subject
    return None


def candidates(conn, subject: str | None, limit: int) -> list:
    rows = conn.execute(
        "SELECT c.source, c.loc, c.title, c.category, c.keywords, c.text FROM cases c "
        "WHERE c.source='人民法院案例库' AND c.text LIKE '%争议焦点%' "
        "AND NOT EXISTS (SELECT 1 FROM case_questions q "
        "  WHERE q.case_source=c.source AND q.case_loc=c.loc) "
        "ORDER BY c.loc").fetchall()
    out = []
    for row in rows:
        s = classify(row)
        if s is None or (subject and s != subject):
            continue
        out.append((s, row))
        if len(out) >= limit:
            break
    return out


def validate(data: dict, relax: bool = False) -> tuple[dict | None, list[str]]:
    """校验 LLM 产物；返回 (可用题目, 问题列表)。

    relax=True 时允许采分点法条暂不可解析（法条库尚未补全时用），
    该点会标记 verified=False，补全后应重新生成或复核。
    """
    if not isinstance(data, dict):
        return None, ["输出不是 JSON 对象"]
    problems: list[str] = []
    stem = (data.get("stem") or "").strip()
    questions = [str(q).strip() for q in (data.get("questions") or [])
                 if str(q).strip()]
    points = data.get("points") or []
    if not MIN_STEM <= len(stem) <= MAX_STEM:
        problems.append(f"题干长度 {len(stem)} 不在 {MIN_STEM}-{MAX_STEM}")
    if not 2 <= len(questions) <= 3:
        problems.append(f"设问数 {len(questions)} 不在 2-3")
    if not 4 <= len(points) <= 8:
        problems.append(f"采分点数 {len(points)} 不在 4-8")
    # 只有「依据」类采分点必须写法条；结论/涵摄/抗辩/程序/救济可以没有
    cleaned, point_problems = clean_points(points, stpl.POINT_KINDS, relax=relax)
    problems.extend(point_problems)
    if problems:
        return None, problems
    return {"subject": data.get("subject") or "", "stem": stem,
            "questions": questions, "points": cleaned,
            "reference": (data.get("reference") or "").strip()}, []


def build_one(row, relax: bool = False) -> tuple[dict | None, list[str]]:
    subject = classify(row) or "民法"
    user = USER_TEMPLATE.format(
        title=row["title"] or "",
        text=(row["text"] or "")[:MAX_CASE_CHARS],
        kind_hint=stpl.kind_hint_for(subject),
        skeleton="\n".join(f"  - {s}" for s in stpl.skeleton_for(subject)))
    return validate(extract_json(ai.call_llm(SYSTEM, user, temperature=0.4)),
                    relax=relax)


def save(conn, row, subject: str, q: dict) -> int:
    return save_question(conn, case_source=row["source"], case_loc=row["loc"],
                         subject=subject, qtype="case", stem=q["stem"],
                         questions=q["questions"], points=q["points"],
                         reference=q["reference"])


def main() -> int:
    ap = argparse.ArgumentParser(description="生成每日案例微主观题")
    ap.add_argument("--subject", help="只生成某一科")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true", help="只生成不落库")
    ap.add_argument("--relax", action="store_true",
                    help="允许采分点法条暂不可解析（法条库补全前用）")
    ap.add_argument("--publish", action="store_true",
                    help="把现有 draft 全部置为 published（人工抽检后使用）")
    args = ap.parse_args()

    conn = db.connect()
    try:
        if args.publish:
            n = publish(conn, "case")
            print(f"已发布 {n} 道题")
            return 0
        todo = candidates(conn, args.subject, args.limit)
        print(f"候选 {len(todo)} 条")
        ok = 0
        for i, (subject, row) in enumerate(todo, 1):
            q, problems = build_one(row, relax=args.relax)
            if q is None:
                print(f"[{i}/{len(todo)}] {row['loc']} 丢弃：{problems[:2]}")
                continue
            q["subject"] = q["subject"] or subject
            if args.dry_run:
                print(f"[{i}/{len(todo)}] {row['loc']} OK（dry-run）"
                      f" 采分点 {len(q['points'])}")
            else:
                save(conn, row, subject, q)
                print(f"[{i}/{len(todo)}] {row['loc']} 已入库 draft"
                      f" 科目={subject} 采分点 {len(q['points'])}")
            ok += 1
        print(f"\n完成：成功 {ok}/{len(todo)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
