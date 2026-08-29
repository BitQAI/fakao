from datetime import date

from fastapi import APIRouter, Depends

from app import db, service

router = APIRouter(prefix="/api", tags=["plans"])


@router.get("/plans/today")
def get_today_plan(conn=Depends(db.get_db)):
    return service.ensure_today_plan(conn, date.today().isoformat())


@router.post("/plans/generate")
def regenerate_plan(conn=Depends(db.get_db)):
    day = date.today().isoformat()
    conn.execute("DELETE FROM daily_plans WHERE date=?", (day,))
    conn.commit()
    return service.ensure_today_plan(conn, day)


@router.get("/listen")
def listen(conn=Depends(db.get_db)):
    data = service.listen_queue(conn)
    data["generating"] = service.ensure_listen_pool(conn)
    return data
