"""错题本：聚合 quiz 答错 + 看背 bad，提供列表与重练队列。"""
from fastapi import APIRouter, Depends

from app import db, stats

router = APIRouter(prefix="/api", tags=["wrongbook"])


@router.get("/wrongbook")
def get_wrongbook(limit: int = 200, conn=Depends(db.get_db)):
    return {"items": stats.wrongbook(conn, min(limit, 500))}


@router.get("/wrongbook/queue")
def get_wrongbook_queue(limit: int = 30, conn=Depends(db.get_db)):
    return {"items": stats.wrongbook_queue(conn, min(limit, 100))}
