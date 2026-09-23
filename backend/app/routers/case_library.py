"""案例库 API：模糊检索、分面浏览、文书化阅读、来源统计、阅读记录。

路径用单数 /api/case/*，与主观题的 /api/cases/{qid} 区分——后者的路径参数是
字符串转换器，会把 /api/cases/search 抢先匹配成 qid 并返回 422。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app import case_facets, case_index, case_views, cases, db

router = APIRouter(prefix="/api", tags=["case-library"])


class ViewIn(BaseModel):
    source: str
    loc: str


def _check_source(source: str) -> str:
    if source not in cases.CASE_SOURCES:
        raise HTTPException(404, "未知案例来源库")
    return source


def _check_common(sort: str, field: str | None, year: str | None,
                  viewed: str) -> None:
    """检索与相邻篇共用的参数校验。"""
    if sort not in case_index.SORTS:
        raise HTTPException(400, f"未知排序方式: {sort}")
    if field and field not in case_facets.FIELD_TAGS + (case_facets.UNLABELED,):
        raise HTTPException(400, f"未知部门法: {field}")
    if year and not (len(year) == 4 and year.isdigit()):
        raise HTTPException(400, "年份需为 4 位数字")
    if viewed not in case_views.VIEWED_FILTERS:
        raise HTTPException(400, f"未知阅读状态: {viewed}")


@router.get("/case/search")
def search_cases(q: str = Query("", max_length=50), source: str | None = None,
                 field: str | None = None, crime: str | None = None,
                 year: str | None = None, sort: str = "relevance",
                 viewed: str = "",
                 limit: int = Query(30, ge=1, le=100),
                 offset: int = Query(0, ge=0), conn=Depends(db.get_db)):
    """检索/浏览：关键词（可空）+ 部门法/罪名/年份/阅读状态筛选 + 排序 + 分页。

    q 为空时是浏览模式（默认按日期倒序），不是空结果；sort=unviewed 未看过优先。
    """
    if source:
        _check_source(source)
    _check_common(sort, field, year, viewed)
    return case_index.search(conn, q, source, field, crime, year, sort, limit, offset,
                             viewed_filter=viewed)


@router.get("/case/neighbors")
def case_neighbors(lib: str, loc: str, q: str = Query("", max_length=50),
                   source: str | None = None, field: str | None = None,
                   crime: str | None = None, year: str | None = None,
                   sort: str = "unviewed", viewed: str = "",
                   conn=Depends(db.get_db)):
    """阅读视图的上一篇/下一篇：按同一检索上下文算出当前篇在全库顺序中的位置。

    lib/loc 是当前篇身份，source 仍是来源库筛选（两者可不同）。
    """
    _check_source(lib)
    if source:
        _check_source(source)
    _check_common(sort, field, year, viewed)
    return case_index.neighbors(conn, lib, loc, q, source, field, crime, year, sort,
                                viewed_filter=viewed)


@router.get("/case/facets")
def list_case_facets(conn=Depends(db.get_db)):
    """分面：部门法 / 罪名 / 年份 / 来源库 的取值与计数。"""
    return case_facets.facets(conn)


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


@router.post("/case/view")
def mark_case_viewed(payload: ViewIn, conn=Depends(db.get_db)):
    """打开阅读视图时打点：首次写入，之后累计 views 并刷新 last_viewed_at。"""
    if cases.get_case(conn, _check_source(payload.source), payload.loc) is None:
        raise HTTPException(404, "案例不存在")
    return case_views.mark_viewed(conn, payload.source, payload.loc)


@router.get("/case/history")
def case_view_history(limit: int = Query(30, ge=1, le=200),
                      conn=Depends(db.get_db)):
    """最近看过的案例（按最近打开时间倒序）。"""
    return case_views.history(conn, limit)


@router.delete("/case/history")
def clear_case_view_history(conn=Depends(db.get_db)):
    """清空阅读记录：「看过」标记与历史一起重置。"""
    return {"cleared": case_views.clear(conn)}
