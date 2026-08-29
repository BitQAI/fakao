from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import db, review_stats, service

router = APIRouter(prefix="/api", tags=["reviews"])


class ReviewIn(BaseModel):
    entry_id: str
    mode: str
    result: str
    duration_sec: int = 0


@router.get("/reviews/history")
def get_review_history(limit: int = 100, mode: str | None = None,
                       conn=Depends(db.get_db)):
    if mode is not None and mode not in {"read", "listen"}:
        raise HTTPException(400, "mode 非法")
    return {"items": review_stats.review_history(
        conn, limit=min(limit, 500), mode=mode)}


@router.get("/leaderboard")
def get_leaderboard(limit: int = 200, sort: str = "total",
                    conn=Depends(db.get_db)):
    if sort not in {"total", "read", "listen"}:
        raise HTTPException(400, "sort 非法")
    return {"items": review_stats.leaderboard(
        conn, limit=min(limit, 500), sort=sort)}


@router.post("/reviews")
def create_review(payload: ReviewIn, conn=Depends(db.get_db)):
    if payload.mode not in {"read", "listen", "quiz"}:
        raise HTTPException(400, "mode 非法")
    if payload.result not in {"good", "fuzzy", "bad", "exposed"}:
        raise HTTPException(400, "result 非法")
    service.record_review(conn, payload.entry_id, payload.mode,
                          payload.result, payload.duration_sec)
    return {"ok": True}
