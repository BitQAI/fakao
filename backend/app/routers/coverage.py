from fastapi import APIRouter, Depends

from app import db, service

router = APIRouter(prefix="/api", tags=["coverage"])


@router.get("/coverage")
def coverage(conn=Depends(db.get_db)):
    return service.coverage_payload(conn)
