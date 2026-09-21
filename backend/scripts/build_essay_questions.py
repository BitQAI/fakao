"""从《法治思想-核心论述》生成第 1 题论述题（材料 + 设问 + 采分点 + 范文提纲）。

与案例分析的区别：材料驱动、没有法条骨架，所以
  - 采分点用论述题维度（总论点/理论依据/材料结合/实践措施/升华），不要求法条；
  - 材料**必须**带 source_quote（资料原话），脚本逐段回查原文——防止编造领导人讲话；
  - 题干是固定作答要求（观点明确、结合材料、不得照搬、600 字以上），不交给模型写。

用法：
    python scripts/build_essay_questions.py --list
    python scripts/build_essay_questions.py --dry-run --limit 2
    python scripts/build_essay_questions.py --topic 依宪治国
    python scripts/build_essay_questions.py --publish        # 抽检后发布
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, subjective_templates as stpl  # noqa: E402
from scripts.subjective_build import (  # noqa: E402
    clean_materials, clean_points, llm_json_checked, missing_kinds, publish,
    save_question)

SOURCE_PATH = Path(config.DATA_DIR) / "科目资料" / "理论法" / "法治思想-核心论述.md"
SOURCE_NAME = "法治思想-核心论述"

MIN_MATERIAL, MAX_MATERIAL = 80, 300
MIN_REFERENCE = 120
#: 专题正文最短字数：低于此值的节（如「共同推进与一体建设」）不单独出题
MIN_TOPIC = 150
#: 论述题必须覆盖的维度（只堆理论不结合材料、或没有措施，都要被打回）
REQUIRED_KINDS = ("总论点", "材料结合", "实践措施")

STEM = ("请阅读以下材料，结合习近平法治思想回答后面的问题。\n"
        "要求：观点明确、表述完整准确；结合材料展开论证，不得照搬材料原文；"
        "分点作答，不少于 600 字（建议 800—1000 字）。")

SYSTEM = ("你是法考主观题第一题（习近平法治思想论述题）的命题助手。"
          "严格输出 JSON，不要任何解释文字。")

USER_TEMPLATE = """下面是备考资料中「{title}」这一节的原文，以及常用金句库片段。

请据此命一道法考主观题第一题（论述题），要求：

1. materials：2—3 段材料，每段 {min_m}-{max_m} 字。材料必须**改编自上面资料的内容**
   （可压缩、可合并、可换表述），**不得编造领导人讲话原文、会议名称或文件表述**；
   每段材料附 source_quote，填资料中对应的一句原话（必须逐字来自资料，用于回查）。
   材料之间要有层次：可分别取「理论论断 / 政策要求 / 实践做法」。
2. questions：1—2 个设问，直接问「谈谈你对……的认识/看法」或「如何……」，不要给答案。
3. points：{min_p}—{max_p} 个采分点，每个带 kind，取值只能是
   总论点 / 理论依据 / 材料结合 / 实践措施 / 升华；
   **必须同时包含 总论点、材料结合、实践措施**，
   其中「材料结合」类要写清结合的是哪一段材料说明了什么，
   「实践措施」类要落到具体环节（立法、执法、司法、守法、监督等）。
   points 不要填 statutes（法治思想没有条文依据）。
4. reference：范文提纲，{min_ref} 字以上，按「总论点 → 理论依据 → 材料结合 →
   实践措施 → 升华」分段给要点，并标注可用金句。

答题结构参考：
{skeleton}

只输出如下 JSON：
{{"materials":[{{"text":"……","source_quote":"……"}}],
  "questions":["……"],
  "points":[{{"no":1,"kind":"总论点","text":"……"}}],
  "reference":"……"}}

【本节原文：{title}】
{section}

【金句库片段】
{quotes}
"""


def load_source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def load_topics(text: str, min_chars: int = MIN_TOPIC) -> list[dict]:
    """抽取可出题的专题：「十二个坚持」（12 节）+「重点专题论述」（9 节）。"""
    lines = text.splitlines()
    topics: list[dict] = []
    chapter, title, buf, keep = "", None, [], False
    wanted = ("十二个坚持", "重点专题论述")

    def flush():
        body = "\n".join(buf).strip()
        if keep and title and len(body) >= min_chars:
            topics.append({"section": chapter, "title": title, "text": body})

    for line in lines:
        if line.startswith("## "):
            flush()
            chapter, title, buf = line[3:].strip(), None, []
            keep = any(w in chapter for w in wanted)
        elif line.startswith("### "):
            flush()
            title, buf = line[4:].strip(), []
        else:
            buf.append(line)
    flush()
    return topics


def load_quotes(text: str, limit: int = 2400) -> str:
    """金句库片段：喂给出题模型，避免它自造「金句」。"""
    marker = "常用金句库"
    i = text.find(marker)
    return text[i:i + limit] if i >= 0 else ""


def validate(data: dict, source: str) -> tuple[dict | None, list[str]]:
    """校验 LLM 产物；材料必须能回查到资料原文。"""
    if not isinstance(data, dict):
        return None, ["输出不是 JSON 对象"]
    problems: list[str] = []
    spec = stpl.SPECS["essay"]

    raw_materials = data.get("materials") or []
    materials, mat_problems = clean_materials(raw_materials, MIN_MATERIAL, MAX_MATERIAL)
    problems.extend(mat_problems)
    if not spec["min_materials"] <= len(materials) <= spec["max_materials"]:
        problems.append(f"材料段数 {len(materials)} 不在 "
                        f"{spec['min_materials']}-{spec['max_materials']}")
    problems.extend(_check_quotes(raw_materials, source))

    questions = [str(q).strip() for q in (data.get("questions") or [])
                 if str(q).strip()]
    if not spec["min_questions"] <= len(questions) <= spec["max_questions"]:
        problems.append(f"设问数 {len(questions)} 不在 "
                        f"{spec['min_questions']}-{spec['max_questions']}")

    points = data.get("points") or []
    if not spec["min_points"] <= len(points) <= spec["max_points"]:
        problems.append(f"采分点数 {len(points)} 不在 "
                        f"{spec['min_points']}-{spec['max_points']}")
    cleaned, point_problems = clean_points(points, stpl.ESSAY_KINDS, must_cite=())
    problems.extend(point_problems)
    lack = missing_kinds(cleaned, REQUIRED_KINDS)
    if lack:
        problems.append(f"采分点缺少维度：{'、'.join(lack)}")

    reference = (data.get("reference") or "").strip()
    if len(reference) < MIN_REFERENCE:
        problems.append(f"范文提纲 {len(reference)} 字，少于 {MIN_REFERENCE}")
    if problems:
        return None, problems
    return {"materials": materials, "questions": questions,
            "points": cleaned, "reference": reference}, []


def _check_quotes(raw_materials: list, source: str) -> list[str]:
    """source_quote 必须是资料里的原话（归一化后做子串匹配），否则该段不合格。"""
    flat = stpl.squash(source)
    problems = []
    for i, m in enumerate(raw_materials or [], 1):
        quote = stpl.squash(str((m or {}).get("source_quote") or ""))
        if len(quote) < 10:
            problems.append(f"第 {i} 段材料缺 source_quote（或用词过短无法回查）")
        elif quote not in flat:
            problems.append(f"第 {i} 段材料的 source_quote 在资料中查不到，疑似编造")
    return problems


def build_one(topic: dict, source: str, quotes: str) -> tuple[dict | None, list[str]]:
    spec = stpl.SPECS["essay"]
    user = USER_TEMPLATE.format(
        title=topic["title"], section=topic["text"], quotes=quotes,
        min_m=MIN_MATERIAL, max_m=MAX_MATERIAL, min_ref=MIN_REFERENCE,
        min_p=spec["min_points"], max_p=spec["max_points"],
        skeleton="\n".join(f"  - {s}" for s in stpl.ESSAY_SKELETON))
    return llm_json_checked(SYSTEM, user, lambda d: validate(d, source),
                            attempts=3, temperature=0.5, max_tokens=2400)


def loc_for(topic: dict) -> str:
    """稳定的定位符：同一专题重复生成不会产生重复行。"""
    slug = topic["title"].replace(" ", "").replace("——", "-")
    return f"essay-{slug[:40]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成法治思想论述题")
    ap.add_argument("--topic", help="只做标题含该关键词的专题")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="只生成不落库")
    ap.add_argument("--list", action="store_true", help="只列专题")
    ap.add_argument("--publish", action="store_true", help="把 essay draft 全部发布")
    args = ap.parse_args()

    if not SOURCE_PATH.exists():
        print(f"缺少资料文件：{SOURCE_PATH}")
        return 1
    source = load_source()
    topics = load_topics(source)
    if args.topic:
        topics = [t for t in topics if args.topic in t["title"]]
    if args.list:
        for t in topics:
            print(f"{t['section']} / {t['title']}（{len(t['text'])} 字）")
        return 0

    conn = db.connect()
    try:
        if args.publish:
            print(f"已发布 {publish(conn, 'essay')} 道论述题")
            return 0
        todo = topics[: args.limit]
        print(f"候选专题 {len(todo)} 个")
        quotes = load_quotes(source)
        done = 0
        for i, topic in enumerate(todo, 1):
            q, problems = build_one(topic, source, quotes)
            if q is None:
                print(f"[{i}/{len(todo)}] {topic['title']} 丢弃：{problems[:2]}")
                continue
            if args.dry_run:
                print(f"[{i}/{len(todo)}] {topic['title']} OK（dry-run）"
                      f" 材料 {len(q['materials'])} 段 采分点 {len(q['points'])}")
            else:
                qid = save_question(
                    conn, case_source=SOURCE_NAME, case_loc=loc_for(topic),
                    subject="理论法", qtype="essay", stem=STEM,
                    questions=q["questions"], points=q["points"],
                    reference=q["reference"], materials=q["materials"])
                if qid:
                    print(f"[{i}/{len(todo)}] {topic['title']} 已入库 draft id={qid}"
                          f" 采分点 {len(q['points'])}")
                else:
                    print(f"[{i}/{len(todo)}] {topic['title']} 已存在，跳过")
            done += 1
        print(f"\n完成：成功 {done}/{len(todo)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
