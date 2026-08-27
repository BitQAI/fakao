from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import db, service

router = APIRouter(prefix="/api", tags=["quizzes"])


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
    q = conn.execute("SELECT id, qtype, answer FROM quizzes WHERE id=?",
                     (payload.quiz_id,)).fetchone()
    if q is None:
        raise HTTPException(404, "题目不存在")
    if q["qtype"] == "choice":
        correct = (payload.user_answer or "").strip().upper() == q["answer"].strip().upper()
    else:
        correct = bool(payload.correct)
    service.record_quiz_answer(conn, payload.quiz_id, payload.user_answer,
                               correct, payload.duration_sec)
    return {"correct": correct, "answer": q["answer"]}
