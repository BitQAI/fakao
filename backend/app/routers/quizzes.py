from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import db, service

router = APIRouter(prefix="/api", tags=["quizzes"])


def _norm_answer(s: str) -> str:
    """单选/多选答案归一化：去空格、大写、排序、去重（"BA"→"AB"）。"""
    return "".join(sorted(set((s or "").strip().upper())))


class QuizAnswerIn(BaseModel):
    quiz_id: int
    user_answer: str = ""
    correct: bool | None = None
    duration_sec: int = 0


@router.get("/quiz/today")
def get_quiz(conn=Depends(db.get_db)):
    return {"questions": service.build_daily_quiz(conn, date.today().isoformat())}


@router.post("/quiz/answer")
def answer_quiz(payload: QuizAnswerIn, conn=Depends(db.get_db)):
    q = conn.execute("SELECT id, qtype, answer, analysis FROM quizzes WHERE id=?",
                     (payload.quiz_id,)).fetchone()
    if q is None:
        raise HTTPException(404, "题目不存在")
    if q["qtype"] == "choice":
        correct = _norm_answer(payload.user_answer) == _norm_answer(q["answer"])
    else:
        correct = bool(payload.correct)
    service.record_quiz_answer(conn, payload.quiz_id, payload.user_answer,
                               correct, payload.duration_sec)
    return {"correct": correct, "answer": q["answer"],
            "analysis": q["analysis"] or ""}
