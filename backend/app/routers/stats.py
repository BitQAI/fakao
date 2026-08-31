"""学习统计：日聚合、掌握度、连胜（供报告页「统计」与今日页进度环）。"""
from fastapi import APIRouter, Depends

from app import db, stats

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats/overview")
def get_overview(days: int = 90, conn=Depends(db.get_db)):
    return stats.overview(conn, min(days, 180))
