from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, quiz_service

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


@router.get("/quiz/today")
def get_quiz(conn=Depends(db.get_db)):
    return {"questions": quiz_service.build_daily_quiz(conn, date.today().isoformat())}


@router.get("/quiz/history")
def get_quiz_history(limit: int = 50, conn=Depends(db.get_db)):
    return {"items": quiz_service.quiz_history(conn, min(max(limit, 1), 200))}


@router.post("/quiz/custom")
def custom_quiz(payload: QuizCustomIn, conn=Depends(db.get_db)):
    return quiz_service.custom_quiz(conn, payload.subjects, payload.points,
                                    payload.limit, payload.timed)


@router.post("/quiz/answer")
def answer_quiz(payload: QuizAnswerIn, conn=Depends(db.get_db)):
    q = conn.execute("SELECT id, entry_id, qtype, answer, analysis FROM quizzes WHERE id=?",
                     (payload.quiz_id,)).fetchone()
    if q is None:
        raise HTTPException(404, "题目不存在")
    if q["qtype"] == "choice":
        correct = _norm_answer(payload.user_answer) == _norm_answer(q["answer"])
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
