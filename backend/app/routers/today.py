from datetime import date

from fastapi import APIRouter, Depends

from app import db, service

router = APIRouter(prefix="/api", tags=["today"])


@router.get("/today")
def get_today(conn=Depends(db.get_db)):
    day = date.today().isoformat()
    return {
        "date": day,
        "days_left": service.days_left(conn, day),
        "plan": service.ensure_today_plan(conn, day),
        "stats": service.today_stats(conn, day),
        "morning_report": service.morning_report(conn, day),
    }
