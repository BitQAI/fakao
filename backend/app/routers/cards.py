"""法条卡接口：法条页挂题时标记「练过」，供自测轮转（看背/听学已改走条目队列）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import db, statute_cards

router = APIRouter(prefix="/api/cards", tags=["cards"])


class CardSeenIn(BaseModel):
    quiz_id: int
    mode: str = "read"


@router.post("/seen")
def mark_card_seen(payload: CardSeenIn, conn=Depends(db.get_db)):
    """标记某道法条题已练（决定自测里「未练过优先」的轮转顺序）。"""
    if payload.mode not in statute_cards.MODES:
        payload.mode = "quiz"
    statute_cards.mark_seen(conn, payload.quiz_id, payload.mode)
    return {"ok": True}
