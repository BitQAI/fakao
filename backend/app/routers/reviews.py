from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import db, service

router = APIRouter(prefix="/api", tags=["reviews"])


class ReviewIn(BaseModel):
    entry_id: str
    mode: str
    result: str
    duration_sec: int = 0


@router.post("/reviews")
def create_review(payload: ReviewIn, conn=Depends(db.get_db)):
    if payload.mode not in {"read", "listen", "quiz"}:
        raise HTTPException(400, "mode 非法")
    if payload.result not in {"good", "fuzzy", "bad", "exposed"}:
        raise HTTPException(400, "result 非法")
    service.record_review(conn, payload.entry_id, payload.mode,
                          payload.result, payload.duration_sec)
    return {"ok": True}
