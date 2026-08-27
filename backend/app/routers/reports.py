from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app import db, service

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports/latest")
def latest(kind: str, conn=Depends(db.get_db)):
    if kind not in {"morning", "evening"}:
        raise HTTPException(400, "kind 非法")
    return service.latest_report(conn, kind)


@router.post("/reports/generate/evening")
def generate_evening(conn=Depends(db.get_db)):
    return service.evening_report(conn, date.today().isoformat(), force=True)
