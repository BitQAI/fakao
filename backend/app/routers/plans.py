from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import db, service

router = APIRouter(prefix="/api", tags=["plans"])


class ContinuePlanIn(BaseModel):
    count: int = Field(default=5, ge=1, le=50)


class ListenMoreIn(BaseModel):
    count: int = Field(default=5, ge=1, le=50)
    exclude: list[str] = []


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


@router.post("/plans/continue")
def continue_plan(payload: ContinuePlanIn, conn=Depends(db.get_db)):
    return {"items": service.continue_plan_entries(conn, payload.count)}


@router.post("/listen/more")
def listen_more(payload: ListenMoreIn, conn=Depends(db.get_db)):
    return service.listen_more(conn, payload.exclude, payload.count)
