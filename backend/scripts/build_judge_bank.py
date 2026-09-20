"""生成「数字判断题」题库（origin='judge'）：数量 / 金额 / 年限 / 人数 / 期限。

两个原料：
  --source statutes  从 data/法条库 抽取含数字表达的条文出题（考点最贴近命题）
  --source entries   从条目结论里含数字表达的考点出题（贴合已学条目）

质量闸门（app.number_terms）：题干里的数字必须能在依据原文中找到；
「错」题只允许改写一处数字。不满足即丢弃，避免 LLM 编造数字。

用法：
    .venv/bin/python scripts/build_judge_bank.py --dry-run
    .venv/bin/python scripts/build_judge_bank.py --source statutes --per-law 3 --limit 40
    .venv/bin/python scripts/build_judge_bank.py --source entries --workers 6
    .venv/bin/python scripts/build_judge_bank.py --publish
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, config, db, number_terms, quiz_bank  # noqa: E402

SYSTEM = "你是法考客观题教练，正在为考生出「数字判断题」（只判断对错，不设选项）。"
_ARTICLE_RE = re.compile(r"(?m)^\s*(第[〇零一二三四五六七八九十百千万0-9]+条)[　\s]*(.*)$")

SUBJECT_RULES: list[tuple[str, str]] = [
    ("刑事诉讼", "刑诉"), ("刑诉", "刑诉"), ("人民检察院刑事诉讼规则", "刑诉"),
    ("公安机关办理刑事案件", "刑诉"), ("认罪认罚", "刑诉"), ("取保候审", "刑诉"),
    ("非法证据", "刑诉"), ("电子数据", "刑诉"), ("量刑程序", "刑诉"),
    ("涉案财物", "刑诉"), ("另案处理", "刑诉"), ("律师执业权利", "刑诉"),
    ("刑法", "刑法"), ("罪名", "刑法"), ("危害", "刑法"), ("盗窃", "刑法"),
    ("诈骗", "刑法"), ("贪污", "刑法"), ("贿赂", "刑法"), ("走私", "刑法"),
    ("赌博", "刑法"), ("洗钱", "刑法"), ("袭警", "刑法"), ("敲诈", "刑法"),
    ("抢", "刑法"), ("卖淫", "刑法"), ("非法利用信息网络", "刑法"),
    # 劳动 / 社会保障在商经知劳环；必须排在「仲裁→民诉」之前，
    # 否则《劳动争议调解仲裁法》会被「仲裁」规则误判成民诉
    ("劳动", "商经知劳环"), ("社会保险", "商经知劳环"), ("工会", "商经知劳环"),
    ("女职工", "商经知劳环"), ("年休假", "商经知劳环"), ("工伤", "商经知劳环"),
    ("民事诉讼法", "民诉"), ("民诉", "民诉"), ("仲裁", "民诉"), ("执行", "民诉"),
    ("财产保全", "民诉"), ("司法拍卖", "民诉"), ("登记立案", "民诉"),
    ("民事调解", "民诉"), ("民事诉讼证据", "民诉"), ("督促程序", "民诉"),
    ("高消费", "民诉"), ("追加当事人", "民诉"), ("互联网法院", "民诉"),
    ("民法典", "民法"), ("担保", "民法"), ("买卖", "民法"), ("商品房", "民法"),
    ("建设工程", "民法"), ("房屋租赁", "民法"), ("民间借贷", "民法"),
    ("物业服务", "民法"), ("人身损害", "民法"), ("道路交通事故", "民法"),
    ("食品药品", "民法"), ("精神损害", "民法"),
    ("行政处罚", "行政法"), ("行政许可", "行政法"), ("行政复议", "行政法"),
    ("行政诉讼法", "行政法"), ("行政强制", "行政法"), ("国家赔偿", "行政法"),
    ("公务员法", "行政法"), ("治安管理处罚", "行政法"), ("政府信息公开", "行政法"),
    ("征收与补偿", "行政法"), ("行政协议", "行政法"), ("行政赔偿", "行政法"),
    ("宪法", "理论法"), ("立法法", "理论法"), ("选举法", "理论法"),
    ("法官法", "理论法"), ("检察官法", "理论法"), ("律师法", "理论法"),
    ("公证法", "理论法"), ("法律援助", "理论法"), ("监察法", "理论法"),
    ("公司法", "商经知劳环"), ("破产", "商经知劳环"), ("票据", "商经知劳环"),
    ("证券", "商经知劳环"), ("保险法", "商经知劳环"), ("海商", "商经知劳环"),
    ("合伙企业", "商经知劳环"), ("个人独资", "商经知劳环"), ("外商投资", "商经知劳环"),
    ("反垄断", "商经知劳环"), ("反不正当竞争", "商经知劳环"), ("消费者权益", "商经知劳环"),
    ("产品质量", "商经知劳环"), ("食品安全", "商经知劳环"),
    ("专利", "商经知劳环"),
    ("商标", "商经知劳环"), ("著作权", "商经知劳环"), ("知识产权", "商经知劳环"),
    ("环境", "商经知劳环"), ("污染", "商经知劳环"), ("土地管理", "商经知劳环"),
    ("房地产", "商经知劳环"), ("生态环境", "商经知劳环"),
    ("公约", "三国法"), ("协定", "三国法"), ("宪章", "三国法"), ("规约", "三国法"),
    ("议定书", "三国法"), ("通则", "三国法"), ("惯例", "三国法"), ("条约", "三国法"),
    ("涉外民事关系", "三国法"),
]


def subject_of(law: str) -> str | None:
    for key, subject in SUBJECT_RULES:
        if key in law:
            return subject
    return None


def article_blocks(text: str) -> list[tuple[str, str]]:
    """切出 [(条号, 正文)]；正文含后续段落直到下一条。"""
    marks = list(_ARTICLE_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start(2):end].strip()
        body = re.sub(r"\s+", "", body)
        if 20 <= len(body) <= 500:
            out.append((m.group(1), body))
    return out


#: 真正值得考的「数」类型（排除公布日期、条号等）
CORE_UNITS = {"日", "天", "个月", "月", "年", "元", "万元", "亿元", "人", "户",
              "份", "倍", "次", "岁", "周岁", "%", "比例", "工作日", "个工作日"}


def _score_article(body: str) -> int:
    return sum(1 for _v, unit, _b in number_terms.extract(body) if unit in CORE_UNITS)


def statute_candidates(per_law: int, skip_basis: set[str]) -> list[dict]:
    """扫描法条库，按法名配额挑选「含数字表达」的条文（数字密度高者优先）。"""
    picked: list[dict] = []
    for path in sorted(config.STATUTE_DIR.glob("*.md")):
        law = path.stem
        subject = subject_of(law)
        if subject is None:
            continue
        text = path.read_text(encoding="utf-8-sig")
        hits = [(no, body) for no, body in article_blocks(text)
                if _score_article(body) > 0
                and f"{law}{no}" not in skip_basis]
        hits.sort(key=lambda item: -_score_article(item[1]))
        for no, body in hits[:per_law]:
            picked.append({"law": law, "no": no, "subject": subject, "text": body})
    return picked


def covered_basis(conn) -> set[str]:
    """已出过题的法条（basis 前缀），避免重复出同一考点。"""
    rows = conn.execute(
        "SELECT basis FROM quizzes WHERE origin=? AND basis != ''",
        (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    return {r["basis"] for r in rows}


_BASIS_NO_RE = re.compile(r"第[〇零一二三四五六七八九十百千万0-9]+条.*$")


def fix_subjects(conn) -> int:
    """按 basis 里的法名重算科目：法条侧题库早期用旧规则，劳动/仲裁类曾误判。"""
    rows = conn.execute(
        "SELECT id, basis, subject FROM quizzes WHERE origin=? AND entry_id IS NULL"
        " AND basis != ''", (quiz_bank.ORIGIN_JUDGE,)).fetchall()
    fixed = 0
    for row in rows:
        law = _BASIS_NO_RE.sub("", row["basis"]).strip()
        if not law:
            continue
        subject = subject_of(law)
        if subject and subject != row["subject"]:
            conn.execute("UPDATE quizzes SET subject=? WHERE id=?",
                         (subject, row["id"]))
            fixed += 1
    conn.commit()
    return fixed


NUM_HINT = re.compile(r"\d|[一二三四五六七八九十百千万]{1,4}(?:日|月|年|元|人|倍|次)")
#: 「自2026年4月7日起施行」这类纯生效日期句：只有日期没有其他数字时不出题
_DATE_ONLY_RE = re.compile(
    r"(?:自|于)?[〇零一二三四五六七八九十百千万0-9]{2,4}年"
    r"[〇零一二三四五六七八九十0-9]{1,3}月[〇零一二三四五六七八九十0-9]{1,3}"
    r"日[^，。；]{0,8}(?:施行|实施|生效)")


def entry_candidates(conn, limit: int) -> list[dict]:
    """条目侧候选：结论里含数字表达的核心考点。"""
    rows = conn.execute(
        "SELECT id, subject, submodule, point, anchor, conclusion, statutes"
        " FROM entries WHERE status='final'").fetchall()
    out = []
    for r in rows:
        text = f"{r['conclusion']}"
        if NUM_HINT.search(text) and number_terms.extract(text):
            out.append({"entry_id": r["id"], "subject": r["subject"],
                        "point": r["point"], "anchor": r["anchor"],
                        "conclusion": text,
                        "statutes": json.loads(r["statutes"] or "[]")})
    return out[:limit] if limit else out


def judge_prompt(reference: str, hint: str) -> str:
    return (
        "下面是一段法考依据原文。请据此出一道「数字判断题」，只考数量/金额/年限/"
        "人数/期限/比例这类数字细节。约束：\n"
        "- stem：一句话陈述句，15~40 字，直接给出一个可判对错的数字结论\n"
        "- answer：\"对\" 或 \"错\"；出「错」题时只改一处数字，其余与原文一致\n"
        "- analysis：30~60 字，点明正确数值与依据\n"
        "- basis：法名+条号（如「刑诉法第91条」），没有则空串\n"
        "只输出 JSON：{\"stem\":\"...\",\"answer\":\"对\",\"analysis\":\"...\","
        "\"basis\":\"...\"}\n\n依据原文：\n" + reference + ("\n\n参考条目：" + hint if hint else "")
    )


def build_one(item: dict) -> tuple[dict, dict | None, str]:
    # 条目侧的题干来自「场景 + 结论」，场景里的数字（判几年、几个月）也属合法依据，
    # 因此校验原文用两者拼接；法条侧直接用条文正文。
    reference = item.get("text") or f"{item['anchor']}。{item['conclusion']}"
    hint = ""
    if item.get("entry_id"):
        hint = f"{item['point']}（场景：{item['anchor']}）"
        if item.get("statutes"):
            hint += "；关联法条：" + "、".join(item["statutes"][:2])
    raw = ai.call_llm(SYSTEM, judge_prompt(reference, hint), temperature=0.5,
                      max_tokens=300)
    quiz = _parse(raw)
    if quiz is None:
        return item, None, "输出不可解析"
    m = _DATE_ONLY_RE.search(quiz["stem"])
    if m and not number_terms.extract(quiz["stem"].replace(m.group(0), "")):
        return item, quiz, "只考生效日期，无实质数字考点"
    ok, why = number_terms.is_grounded(quiz["stem"], reference, quiz["answer"])
    if not ok:
        return item, quiz, why
    return item, quiz, ""


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
    if answer not in ("对", "错") or len(stem) < 10:
        return None
    return {"stem": stem, "answer": answer,
            "analysis": (data.get("analysis") or "").strip(),
            "basis": (data.get("basis") or "").strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成数字判断题题库")
    ap.add_argument("--source", choices=["statutes", "entries", "both"],
                    default="both")
    ap.add_argument("--per-law", type=int, default=3, help="每部法条最多取几条")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--fix-subjects", action="store_true",
                    help="按 basis 里的法名重算科目（法条侧题库科目口径修正）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    conn = db.connect()
    if args.fix_subjects:
        print(f"已修正 {fix_subjects(conn)} 题科目")
        conn.close()
        return 0
    if args.publish:
        n = quiz_bank.set_status(conn, origins=(quiz_bank.ORIGIN_JUDGE,),
                                 status="published")
        print(f"已发布 {n} 题（origin=judge）")
        conn.close()
        return 0

    items: list[dict] = []
    if args.source in ("statutes", "both"):
        statutes = statute_candidates(args.per_law, covered_basis(conn))
        print(f"法条候选 {len(statutes)} 条")
        items += statutes
    if args.source in ("entries", "both"):
        entries = entry_candidates(conn, args.limit)
        print(f"条目候选 {len(entries)} 条")
        items += entries
    if args.limit:
        items = items[:args.limit]
    if args.dry_run:
        by_sub: dict[str, int] = {}
        for it in items:
            by_sub[it["subject"]] = by_sub.get(it["subject"], 0) + 1
        print("科目分布:", by_sub)
        conn.close()
        return 0

    ok = fail = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for i, (item, quiz, why) in enumerate(pool.map(build_one, items), 1):
            if quiz is None or why:
                fail += 1
                print(f"[{i}/{len(items)}] FAIL {why} | "
                      f"{(quiz or {}).get('stem', '')[:40]}")
                continue
            # 法条侧统一用「法名+条号」的规范写法，便于去重与前端跳转
            basis = (f"{item['law']}{item['no']}" if item.get("law")
                     else quiz["basis"])
            quiz_bank.save_question(
                conn, qtype="judge", origin=quiz_bank.ORIGIN_JUDGE,
                entry_id=item.get("entry_id"), subject=item["subject"],
                point=item.get("point", ""), stem=quiz["stem"],
                options=[], answer=quiz["answer"], analysis=quiz["analysis"],
                basis=basis, status="draft")
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
