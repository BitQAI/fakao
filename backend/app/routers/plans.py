from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import db, service

router = APIRouter(prefix="/api", tags=["plans"])


class ContinuePlanIn(BaseModel):
    count: int = Field(default=5, ge=1, le=50)


class ListenMoreIn(BaseModel):
    count: int = Field(default=5, ge=1, le=50)
    exclude: list[str] = []


class CustomRangeIn(BaseModel):
    subjects: list[str] = []
    points: list[str] = []
    limit: int = Field(default=200, ge=1, le=500)
    exclude: list[str] = []


@router.get("/entries/{entry_id}")
def get_entry(entry_id: str, conn=Depends(db.get_db)):
    e = service.entry_by_id(conn, entry_id)
    if e is None:
        raise HTTPException(404, "条目不存在")
    return e


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


@router.post("/plans/custom")
def custom_plan(payload: CustomRangeIn, conn=Depends(db.get_db)):
    items = service.custom_entries(
        conn, payload.subjects, payload.points,
        listen_only=False, exclude=payload.exclude)
    return {"items": items[:payload.limit], "total": len(items)}


@router.post("/listen/custom")
def custom_listen(payload: CustomRangeIn, conn=Depends(db.get_db)):
    items = service.custom_entries(
        conn, payload.subjects, payload.points,
        listen_only=True, exclude=payload.exclude)
    limit = min(payload.limit, 100)
    heard_total = conn.execute(
        """
        SELECT COUNT(DISTINCT r.entry_id) AS n
        FROM reviews r JOIN entries e ON e.id = r.entry_id
        WHERE r.mode='listen' AND e.status='final' AND e.tts_text != ''
        """).fetchone()["n"]
    return {"items": items[:limit], "remaining": len(items),
            "heard_total": heard_total, "generating": False, "custom": True}
