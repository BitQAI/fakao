"""自测题库服务：每日选题、答题记录、解析必达、做题历史。

从 service.py 按职责拆出（service.py 达到 500 行硬上限）。
"""
import json
from datetime import date, datetime

from app import ai
from app.service import _entry_by_id, ensure_today_plan, plan_payload


def record_quiz_answer(conn, quiz_id: int, user_answer: str, correct: bool,
                       duration_sec: int = 0) -> None:
    conn.execute(
        "INSERT INTO quiz_answers (quiz_id, ts, user_answer, correct, duration_sec) "
        "VALUES (?,?,?,?,?)",
        (quiz_id, datetime.now().isoformat(timespec="seconds"),
         user_answer, int(correct), duration_sec),
    )
    conn.commit()


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
               q.entry_id, q.qtype, q.stem, q.options, q.answer, q.analysis
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
            "answer": r["answer"], "analysis": analysis,
        })
    conn.commit()
    return out


def build_daily_quiz(conn, day: str | None = None, limit: int = 10) -> list[dict]:
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
    selected: list[str] = []
    n_today = round(limit * 0.7)
    selected += [i for i in today_ids if i not in selected][:n_today]
    selected += [i for i in wrong_ids
                 if i not in selected and i not in today_ids]
    if len(selected) < limit:
        for i in today_ids:
            if len(selected) >= limit:
                break
            if i not in selected:
                selected.append(i)
    selected = selected[:limit]

    out = []
    for entry_id in selected:
        entry = _entry_by_id(conn, entry_id)
        if entry is None:
            continue
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
        else:
            quiz = ai.generate_quiz(entry) or ai.cloze_quiz(entry)
            cur = conn.execute(
                "INSERT INTO quizzes (entry_id, qtype, stem, options, answer, analysis, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (entry_id, quiz["qtype"], quiz["stem"],
                 json.dumps(quiz["options"], ensure_ascii=False),
                 quiz["answer"], quiz.get("analysis", ""),
                 datetime.now().isoformat(timespec="seconds")),
            )
            quiz = {**quiz, "id": cur.lastrowid, "entry_id": entry_id}
        out.append(quiz)
    conn.commit()
    return out
