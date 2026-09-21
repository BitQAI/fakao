from fastapi import APIRouter, Depends

from app import card_entries, db, stats

router = APIRouter(prefix="/api", tags=["coverage"])


@router.get("/coverage")
def coverage(conn=Depends(db.get_db)):
    return stats.coverage_payload(conn)


@router.get("/coverage/cards")
def card_coverage(conn=Depends(db.get_db)):
    """法条题卡覆盖：科目 → 法条主名 → {count, unread}（自定义范围选题卡用）。"""
    return card_entries.coverage(conn)
