from fastapi import APIRouter, Depends

from app import db, stats

router = APIRouter(prefix="/api", tags=["coverage"])


@router.get("/coverage")
def coverage(conn=Depends(db.get_db)):
    return stats.coverage_payload(conn)
