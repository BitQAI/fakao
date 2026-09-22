"""案例库 API：模糊检索、文书化阅读、来源统计（只读）。

路径用单数 /api/case/*，与主观题的 /api/cases/{qid} 区分——后者的路径参数是
字符串转换器，会把 /api/cases/search 抢先匹配成 qid 并返回 422。
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app import case_index, cases, db

router = APIRouter(prefix="/api", tags=["case-library"])


def _check_source(source: str) -> str:
    if source not in cases.CASE_SOURCES:
        raise HTTPException(404, "未知案例来源库")
    return source


@router.get("/case/search")
def search_cases(q: str = Query("", max_length=50), source: str | None = None,
                 limit: int = Query(30, ge=1, le=100), conn=Depends(db.get_db)):
    """关键词模糊检索：多词 AND，命中标题/案号/关键词/类别/正文。"""
    if source:
        _check_source(source)
    items = case_index.search(conn, q, source, limit)
    return {"items": items, "total": len(items), "query": q.strip()}


@router.get("/case/stats")
def case_stats(conn=Depends(db.get_db)):
    """案例库总量与各来源条数。"""
    return case_index.stats(conn)


@router.get("/case/detail")
def case_detail(source: str, loc: str, conn=Depends(db.get_db)):
    """单篇案例：元数据 + 文书小节（原文按裁判要旨/基本案情/裁判理由等分节）。"""
    rec = cases.get_case(conn, _check_source(source), loc)
    if rec is None:
        raise HTTPException(404, "案例不存在")
    sections, dropped = case_index.sections(rec.pop("text"), rec.get("title", ""))
    return {**rec, "sections": sections, "paragraphs_dropped": dropped}
