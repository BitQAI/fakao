from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import config, db, service

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsIn(BaseModel):
    exam_date: str | None = None
    capacity_max: int | None = None


@router.get("/settings")
def get_settings(conn=Depends(db.get_db)):
    return {
        "exam_date": service.get_setting(conn, "exam_date", ""),
        "capacity_max": int(service.get_setting(conn, "capacity_max", "50") or "50"),
        "deepseek_configured": bool(config.DEEPSEEK_API_KEY),
        "days_left": service.days_left(conn, date.today().isoformat()),
    }


@router.put("/settings")
def update_settings(payload: SettingsIn, conn=Depends(db.get_db)):
    if payload.exam_date is not None:
        try:
            date.fromisoformat(payload.exam_date)
        except ValueError:
            raise HTTPException(400, "exam_date 需为 YYYY-MM-DD")
        service.set_setting(conn, "exam_date", payload.exam_date)
    if payload.capacity_max is not None:
        if not 5 <= payload.capacity_max <= 200:
            raise HTTPException(400, "capacity_max 需在 5-200 之间")
        service.set_setting(conn, "capacity_max", str(payload.capacity_max))
    return get_settings(conn)
