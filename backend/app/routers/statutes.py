"""法条检索 API：法名清单、目录与条文、全文检索、条目反向索引。"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app import db, statute_index

router = APIRouter(prefix="/api", tags=["statutes"])


@router.get("/statutes")
def list_statutes():
    """法名清单（含条数与元信息）。"""
    return {"items": statute_index.list_laws()}


@router.get("/statutes/{law}")
def get_statute_law(law: str, offset: int = Query(0, ge=0),
                    limit: int = Query(200, ge=1, le=1000)):
    """单部法律的目录 + 条文分页。law 为法条库文件主名。"""
    payload = statute_index.law_payload(law, offset, limit)
    if payload is None:
        raise HTTPException(404, "法条库中未收录该法")
    return payload


@router.get("/statute/search")
def search_statute(q: str = Query("", max_length=50),
                   limit: int = Query(30, ge=1, le=100)):
    """条文全文检索。"""
    return {"items": statute_index.search(q, limit)}


@router.get("/statute/entries")
def statute_entries(law: str, no: int = Query(..., ge=1),
                    conn=Depends(db.get_db)):
    """反向索引：引用了「该法该条」的考点条目。"""
    return {"items": statute_index.entries_for(conn, law, no)}
