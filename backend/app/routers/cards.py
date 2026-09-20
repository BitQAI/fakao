"""法条卡接口：看背 / 听学 / 法条页共用的法条驱动题池。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import db, statute_cards

router = APIRouter(prefix="/api/cards", tags=["cards"])


class CardSeenIn(BaseModel):
    quiz_id: int
    mode: str = "read"


@router.get("/statute")
def list_statute_cards(mode: str = "read", limit: int = 10, subjects: str = "",
                       unseen_only: bool = False, conn=Depends(db.get_db)):
    """法条卡（一条法条 + 基于它的题）；mode=read|listen|quiz 各自记进度。"""
    subject_list = [s.strip() for s in subjects.split(",") if s.strip()]
    items = statute_cards.pool(conn, subjects=subject_list or None, mode=mode,
                               limit=max(1, min(limit, 50)),
                               unseen_only=unseen_only)
    return {"items": items, "total": statute_cards.stats(conn)["total"]}


@router.post("/seen")
def mark_card_seen(payload: CardSeenIn, conn=Depends(db.get_db)):
    """标记法条卡已看/已听（决定下次队列的「未看过优先」顺序）。"""
    statute_cards.mark_seen(conn, payload.quiz_id, payload.mode)
    return {"ok": True}


@router.get("/stats")
def card_stats(conn=Depends(db.get_db)):
    return statute_cards.stats(conn)
