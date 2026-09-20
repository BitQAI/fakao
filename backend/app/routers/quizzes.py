from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, quiz_bank, quiz_service

router = APIRouter(prefix="/api", tags=["quizzes"])


def _norm_answer(s: str) -> str:
    """单选/多选答案归一化：去空格、大写、排序、去重（"BA"→"AB"）。"""
    return "".join(sorted(set((s or "").strip().upper())))


class QuizAnswerIn(BaseModel):
    quiz_id: int
    user_answer: str = ""
    correct: bool | None = None
    duration_sec: int = 0


class QuizCustomIn(BaseModel):
    subjects: list[str] = []
    points: list[str] = []
    limit: int = Field(default=10, ge=1, le=50)
    timed: bool = False


class JudgeQuizIn(BaseModel):
    subjects: list[str] = []
    points: list[str] = []
    limit: int = Field(default=10, ge=1, le=50)


@router.get("/quiz/today")
def get_quiz(regenerate: bool = False, conn=Depends(db.get_db)):
    day = date.today().isoformat()
    if regenerate:
        # 只清「当日缓存题」：题库题（bank/judge）是离线生成的资产，同日重建时不能误删
        conn.execute(
            "DELETE FROM quiz_answers WHERE quiz_id IN "
            "(SELECT id FROM quizzes WHERE date(created_at)=? AND origin='daily')",
            (day,),
        )
        conn.execute("DELETE FROM quizzes WHERE date(created_at)=? AND origin='daily'",
                     (day,))
        conn.commit()
    return {"questions": quiz_service.build_daily_quiz(conn, day)}


@router.get("/quiz/history")
def get_quiz_history(limit: int = 50, conn=Depends(db.get_db)):
    return {"items": quiz_service.quiz_history(conn, min(max(limit, 1), 200))}


@router.post("/quiz/custom")
def custom_quiz(payload: QuizCustomIn, conn=Depends(db.get_db)):
    return quiz_service.custom_quiz(conn, payload.subjects, payload.points,
                                    payload.limit, payload.timed)


@router.post("/quiz/judge")
def judge_quiz(payload: JudgeQuizIn, conn=Depends(db.get_db)):
    """数字判断专项（数量/金额/年限/人数）：从 judge 题库抽题。"""
    return quiz_service.judge_quiz(conn, payload.subjects, payload.points,
                                   payload.limit)


@router.get("/quiz/bank/stats")
def quiz_bank_stats(conn=Depends(db.get_db)):
    """题库概览：按 origin/qtype/status 计数。"""
    return {"items": quiz_bank.stats(conn)}


@router.post("/quiz/answer")
def answer_quiz(payload: QuizAnswerIn, conn=Depends(db.get_db)):
    q = conn.execute("SELECT id, entry_id, qtype, answer, analysis FROM quizzes WHERE id=?",
                     (payload.quiz_id,)).fetchone()
    if q is None:
        raise HTTPException(404, "题目不存在")
    if q["qtype"] == "choice":
        correct = _norm_answer(payload.user_answer) == _norm_answer(q["answer"])
    elif q["qtype"] == "judge":
        picked = quiz_bank.normalize_judge_answer(payload.user_answer)
        correct = picked is not None and picked == q["answer"]
    else:
        correct = bool(payload.correct)
    quiz_service.record_quiz_answer(conn, payload.quiz_id, payload.user_answer,
                                    correct, payload.duration_sec)
    analysis = quiz_service.ensure_quiz_analysis(conn, {
        "id": q["id"], "entry_id": q["entry_id"], "qtype": q["qtype"],
        "answer": q["answer"], "analysis": q["analysis"] or "",
    })
    return {"correct": correct, "answer": q["answer"],
            "analysis": analysis}
