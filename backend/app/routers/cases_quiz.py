"""主观题 API：今日题（案例分析/论述题/综合大案例）、作答、判分、复盘。"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import case_quiz, db, tts

router = APIRouter(prefix="/api", tags=["cases-quiz"])

#: 题型取值（与 case_questions.qtype 的 CHECK 约束一致）
QuestionType = Literal["case", "essay", "composite"]


class AnswerIn(BaseModel):
    answer_text: str = ""
    duration_sec: int = 0
    mode: str = "write"


class GradeIn(BaseModel):
    hit_points: list[int] = Field(default_factory=list)


@router.get("/cases/daily")
def daily_case(type: QuestionType = "case", conn=Depends(db.get_db)):
    """今日题（不含参考答案与采分点）。type=case|essay|composite。"""
    q = case_quiz.pick_daily(conn, qtype=type)
    return {"question": case_quiz.public_payload(q) if q else None,
            "stats": case_quiz.stats_summary(conn, type)}


@router.get("/cases/history")
def case_history(limit: int = Query(50, ge=1, le=200),
                 type: QuestionType | None = None,
                 conn=Depends(db.get_db)):
    return {"items": case_quiz.history(conn, limit, type),
            "stats": case_quiz.stats_summary(conn, type)}


@router.get("/cases/misses")
def case_misses(subject: str | None = None,
                type: QuestionType | None = None,
                limit: int = Query(200, ge=1, le=500),
                conn=Depends(db.get_db)):
    """复盘池：未命中的采分点，按文本聚合。"""
    return {"items": case_quiz.misses(conn, subject, limit, type)}


@router.get("/cases/{qid}")
def case_detail(qid: int, conn=Depends(db.get_db)):
    """单题详情（含参考答案与采分点，复习用）。"""
    q = case_quiz.question_by_id(conn, qid)
    if q is None:
        raise HTTPException(404, "案例题不存在")
    return q


@router.get("/cases/{qid}/audio")
def case_audio(qid: int, conn=Depends(db.get_db)):
    """「只听」模式音频：题干与设问，不含答案与采分点。"""
    q = case_quiz.question_by_id(conn, qid)
    if q is None:
        raise HTTPException(404, "案例题不存在")
    path = tts.ensure_mp3(f"case-{qid}", case_quiz.listen_text(q))
    if not path.exists():
        raise HTTPException(503, "音频生成中，请稍后重试")
    media_type = "audio/wav" if path.suffix == ".wav" else "audio/mpeg"
    return FileResponse(path, media_type=media_type)


@router.post("/cases/{qid}/answer")
def submit_answer(qid: int, body: AnswerIn, conn=Depends(db.get_db)):
    """提交要点，返回采分点核对表（此时才下发采分点）。"""
    if body.mode not in ("write", "listen"):
        raise HTTPException(422, "mode 只能是 write 或 listen")
    result = case_quiz.submit_answer(conn, qid, body.answer_text,
                                     body.duration_sec, body.mode)
    if result is None:
        raise HTTPException(404, "案例题不存在")
    return result


@router.post("/cases/{qid}/grade")
def grade_answer(qid: int, body: GradeIn, conn=Depends(db.get_db)):
    """提交勾选结果：得分 + 未命中采分点及其法条依据。"""
    result = case_quiz.grade(conn, qid, body.hit_points)
    if result is None:
        raise HTTPException(404, "案例题不存在")
    return result
