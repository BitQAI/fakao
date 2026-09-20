"""自测题库服务：每日选题、答题记录、解析必达、做题历史。

从 service.py 按职责拆出（service.py 达到 500 行硬上限）。
"""
import json
from datetime import date, datetime

from app import ai
from app import quiz_bank
from app import statute_cards
from app.service import _entry_by_id, ensure_today_plan, plan_payload


def record_quiz_answer(conn, quiz_id: int, user_answer: str, correct: bool,
                       duration_sec: int = 0) -> None:
    conn.execute(
        "INSERT INTO quiz_answers (quiz_id, ts, user_answer, correct, duration_sec) "
        "VALUES (?,?,?,?,?)",
        (quiz_id, datetime.now().isoformat(timespec="seconds"),
         user_answer, int(correct), duration_sec),
    )
    row = conn.execute("SELECT entry_id FROM quizzes WHERE id=?",
                       (quiz_id,)).fetchone()
    if row is not None and row["entry_id"] is None:
        statute_cards.mark_seen(conn, quiz_id, "quiz")   # 练过的法条题排到队尾
    conn.commit()


def _card_to_question(conn, card: dict) -> dict:
    """法条卡 → 答题接口的题目结构（entry_id 为空，basis 供前端显示依据）。"""
    quiz = {"id": card["quiz_id"], "entry_id": None, "subject": card["subject"],
            "point": "", "qtype": card["qtype"], "stem": card["stem"],
            "options": card["options"], "answer": card["answer"],
            "analysis": card["analysis"], "basis": card["basis"], "variant": ""}
    quiz["analysis"] = ensure_quiz_analysis(conn, quiz)
    return quiz


def ensure_quiz_analysis(conn, quiz: dict, persist: bool = True) -> str:
    """保证题目恒有解析：非空直接返回；为空则 LLM 懒生成，失败用兜底并回写。"""
    analysis = (quiz.get("analysis") or "").strip()
    if analysis:
        return analysis
    analysis = (ai.generate_quiz_analysis(quiz) or "").strip()
    if not analysis:
        ans = (quiz.get("answer") or "").strip()
        if quiz.get("qtype") == "cloze":
            analysis = ans or "无"
        else:
            analysis = f"正确答案：{ans}。" if ans else "无"
        entry = _entry_by_id(conn, quiz.get("entry_id") or "")
        if entry and entry["conclusion"]:
            analysis += f"考点结论：{entry['conclusion']}"
    if persist and quiz.get("id"):
        conn.execute("UPDATE quizzes SET analysis=? WHERE id=?",
                     (analysis, quiz["id"]))
    return analysis


def quiz_history(conn, limit: int = 50) -> list[dict]:
    """最近做题记录：题干、选项、正确答案、用户所选字母与选项文本、对错、解析。"""
    rows = conn.execute(
        """
        SELECT qa.id AS answer_id, qa.quiz_id, qa.ts, qa.user_answer, qa.correct,
               q.entry_id, q.qtype, q.stem, q.options, q.answer, q.analysis, q.basis
        FROM quiz_answers qa JOIN quizzes q ON qa.quiz_id=q.id
        ORDER BY qa.ts DESC, qa.id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        options = json.loads(r["options"] or "[]")
        picked = (r["user_answer"] or "").strip().upper()
        picked_texts = [
            opt for i, opt in enumerate(options)
            if chr(65 + i) in picked
        ]
        analysis = ensure_quiz_analysis(conn, {
            "id": r["quiz_id"], "entry_id": r["entry_id"], "qtype": r["qtype"],
            "stem": r["stem"], "options": options, "answer": r["answer"],
            "analysis": r["analysis"] or "",
        })
        out.append({
            "answer_id": r["answer_id"], "quiz_id": r["quiz_id"],
            "ts": r["ts"], "user_answer": picked,
            "picked_texts": picked_texts, "correct": bool(r["correct"]),
            "qtype": r["qtype"], "stem": r["stem"], "options": options,
            "answer": r["answer"], "analysis": analysis, "basis": r["basis"] or "",
        })
    conn.commit()
    return out


def build_daily_quiz(conn, day: str | None = None, limit: int = 10) -> list[dict]:
    """今日自测：条目题为主，每 3 题留 1 题给法条驱动题（未练过优先）。

    法条驱动题（entry_id 为空）此前只能靠「组卷」遇到，这里让每日必修路径也覆盖它们。
    """
    day = day or date.today().isoformat()
    ensure_today_plan(conn, day)
    plan = plan_payload(conn, day)
    today_ids = [it["id"] for it in plan["items"]]
    wrong_ids = [
        r["entry_id"] for r in conn.execute(
            "SELECT DISTINCT q.entry_id FROM quiz_answers qa "
            "JOIN quizzes q ON qa.quiz_id=q.id "
            "WHERE qa.correct=0 AND q.entry_id IS NOT NULL"
        ).fetchall()
    ]
    statute_quota = limit // 3
    entry_slots = max(1, limit - statute_quota)
    selected: list[str] = []
    n_today = round(entry_slots * 0.7)
    selected += [i for i in today_ids if i not in selected][:n_today]
    selected += [i for i in wrong_ids
                 if i not in selected and i not in today_ids]
    if len(selected) < entry_slots:
        for i in today_ids:
            if len(selected) >= entry_slots:
                break
            if i not in selected:
                selected.append(i)
    selected = selected[:entry_slots]

    out = []
    for entry_id in selected:
        entry = _entry_by_id(conn, entry_id)
        if entry is None:
            continue
        out.append(_quiz_for_entry(conn, entry, day))
    if len(out) < limit and statute_quota:
        focus = list(dict.fromkeys(
            it["subject"] for it in plan["items"] if it.get("subject")))
        for card in statute_cards.pool(conn, subjects=focus or None, mode="quiz",
                                       limit=limit - len(out)):
            out.append(_card_to_question(conn, card))
    conn.commit()
    return out


def _quiz_for_entry(conn, entry: dict, day: str) -> dict:
    """取/建题目：优先题库已发布题，其次当日缓存，最后才现生成（省 LLM）。"""
    entry_id = entry["id"]
    banked = quiz_bank.question_for_entry(conn, entry_id)
    if banked is not None:
        banked["analysis"] = ensure_quiz_analysis(conn, banked)
        return banked
    cached = conn.execute(
        "SELECT id, qtype, stem, options, answer, analysis FROM quizzes "
        "WHERE entry_id=? AND date(created_at)=?", (entry_id, day)
    ).fetchone()
    if cached:
        quiz = {"id": cached["id"], "entry_id": entry_id,
                "qtype": cached["qtype"], "stem": cached["stem"],
                "options": json.loads(cached["options"] or "[]"),
                "answer": cached["answer"], "analysis": cached["analysis"] or ""}
        quiz["analysis"] = ensure_quiz_analysis(conn, quiz)
        return quiz
    quiz = ai.generate_quiz(entry) or ai.cloze_quiz(entry)
    cur = conn.execute(
        "INSERT INTO quizzes (entry_id, qtype, stem, options, answer, analysis, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (entry_id, quiz["qtype"], quiz["stem"],
         json.dumps(quiz["options"], ensure_ascii=False),
         quiz["answer"], quiz.get("analysis", ""),
         datetime.now().isoformat(timespec="seconds")),
    )
    return {**quiz, "id": cur.lastrowid, "entry_id": entry_id}


def judge_quiz(conn, subjects: list[str] | None = None,
               points: list[str] | None = None, limit: int = 10) -> dict:
    """数字判断专项：从 judge 题库抽题（只取已发布题）。"""
    questions = quiz_bank.pick(
        conn, origins=(quiz_bank.ORIGIN_JUDGE,), limit=limit,
        subjects=subjects, points=points, qtypes=["judge"],
    )
    return {"questions": questions, "total": len(questions)}


#: 题库补齐的抽题池倍数：先随机取大池再按配额分流，
#: 否则 limit 很小时随机抽样可能一条法条题都抽不到，配额形同虚设
_POOL_FACTOR = 4


def _fill_order(conn, subjects: list[str], points: list[str], limit: int,
                statute_quota: int) -> list[dict]:
    """题库补齐顺序：先按配额放法条驱动题（basis 有值、entry_id 为空），再放其余题。"""
    pool = quiz_bank.pick(conn, origins=(quiz_bank.ORIGIN_BANK,),
                          limit=max(limit, limit * _POOL_FACTOR),
                          subjects=subjects or None, points=points or None)
    statute = [q for q in pool if not q.get("entry_id")]
    others = [q for q in pool if q.get("entry_id")]
    return statute[:statute_quota] + others + statute[statute_quota:]


def custom_quiz(conn, subjects: list[str], points: list[str],
                limit: int = 10, timed: bool = False) -> dict:
    """智能组卷：按科目/知识点过滤（复用自定义范围排序），题目优先题库。

    条目题不足题量时，从题库补齐（会带出法条驱动题：basis 有值、entry_id 为空），
    让「法条库 → 题库」的扩容真正能被练到。
    """
    from app.service import custom_entries

    day = date.today().isoformat()
    # 每 3 题留 1 题给法条驱动题（basis 有值、entry_id 为空），
    # 否则组卷永远只出条目题，法条库补全的内容练不到。
    statute_quota = limit // 3
    entries = custom_entries(conn, subjects, points,
                             limit=max(1, limit - statute_quota))
    questions = [_quiz_for_entry(conn, e, day)
                 for e in entries[:max(0, limit - statute_quota)]]
    if len(questions) < limit:
        seen = {q["id"] for q in questions}
        for q in _fill_order(conn, subjects, points, limit, statute_quota):
            if len(questions) >= limit:
                break
            if q["id"] in seen:
                continue
            questions.append(q)
            seen.add(q["id"])
    conn.commit()
    return {"questions": questions, "timed": timed, "total": len(questions)}
