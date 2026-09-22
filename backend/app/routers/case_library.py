"""案例库 API：模糊检索、分面浏览、文书化阅读、来源统计（只读）。

路径用单数 /api/case/*，与主观题的 /api/cases/{qid} 区分——后者的路径参数是
字符串转换器，会把 /api/cases/search 抢先匹配成 qid 并返回 422。
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app import case_facets, case_index, cases, db

router = APIRouter(prefix="/api", tags=["case-library"])


def _check_source(source: str) -> str:
    if source not in cases.CASE_SOURCES:
        raise HTTPException(404, "未知案例来源库")
    return source


@router.get("/case/search")
def search_cases(q: str = Query("", max_length=50), source: str | None = None,
                 field: str | None = None, crime: str | None = None,
                 year: str | None = None, sort: str = "relevance",
                 limit: int = Query(30, ge=1, le=100),
                 offset: int = Query(0, ge=0), conn=Depends(db.get_db)):
    """检索/浏览：关键词（可空）+ 部门法/罪名/年份筛选 + 排序 + 分页。

    q 为空时是浏览模式（默认按日期倒序），不是空结果。
    """
    if source:
        _check_source(source)
    if sort not in case_index.SORTS:
        raise HTTPException(400, f"未知排序方式: {sort}")
    if field and field not in case_facets.FIELD_TAGS + (case_facets.UNLABELED,):
        raise HTTPException(400, f"未知部门法: {field}")
    if year and not (len(year) == 4 and year.isdigit()):
        raise HTTPException(400, "年份需为 4 位数字")
    return case_index.search(conn, q, source, field, crime, year, sort, limit, offset)


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
