/** 案例库「阅读上下文」：列表的检索词与筛选口径。
 *
 *  进 URL 才能让阅读视图（/cases?lib=&loc=）算出上一篇/下一篇，并在返回列表时保留筛选。
 */
import {
  DEFAULT_CASE_SORT, type CaseFilters, type CaseSort, type CaseViewedFilter,
} from "@/lib/caseLibTypes";

/** 只需 get 的最小接口：兼容 URLSearchParams 与 next/navigation 的只读参数。 */
export interface ParamReader {
  get(key: string): string | null;
}

/** 阅读上下文 = 检索词 + 列表筛选（口径与 /api/case/search 一致）。 */
export interface ReaderContext extends CaseFilters {
  q: string;
}

/** 默认上下文：历史记录跳转等「无筛选」场景用它，保证前后篇一定能算出来。 */
export const EMPTY_READER_CONTEXT: ReaderContext = {
  q: "", source: "", field: "", crime: "", year: "", viewed: "", sort: DEFAULT_CASE_SORT,
};

const SORTS: CaseSort[] = ["unviewed", "relevance", "newest", "oldest"];

export function filtersFromParams(params: ParamReader): CaseFilters {
  return {
    source: params.get("source") ?? "",
    field: params.get("field") ?? "",
    crime: params.get("crime") ?? "",
    year: params.get("year") ?? "",
    viewed: asViewed(params.get("viewed")),
    sort: asSort(params.get("sort")),
  };
}

export function readerContextFromParams(params: ParamReader): ReaderContext {
  return { q: params.get("q") ?? "", ...filtersFromParams(params) };
}

/** 列表页 URL（返回案例库时保留检索词与筛选）。 */
export function listPath(q: string, filters: CaseFilters): string {
  const sp = buildParams({ q, ...filters });
  return `/cases${sp ? `?${sp}` : ""}`;
}

/** 阅读视图 URL。 */
export function readerPath(ctx: ReaderContext, lib: string, loc: string): string {
  return `/cases?${buildParams({ ...ctx, lib, loc })}`;
}

/** 列表检索接口路径。 */
export function searchPath(q: string, filters: CaseFilters, offset: number,
                           limit: number): string {
  const sp = new URLSearchParams({
    limit: String(limit), offset: String(offset), sort: filters.sort,
  });
  if (q.trim()) sp.set("q", q.trim());
  return `/api/case/search?${withFilters(sp, filters)}`;
}

/** 前后篇接口路径；`lib`/`loc` 是当前篇身份，`source` 仍是来源库筛选。 */
export function neighborPath(ctx: ReaderContext, lib: string, loc: string): string {
  const sp = new URLSearchParams({ lib, loc, sort: ctx.sort });
  if (ctx.q.trim()) sp.set("q", ctx.q.trim());
  return `/api/case/neighbors?${withFilters(sp, ctx)}`;
}

/** 把非空筛选挂到参数上（阅读状态为空 = 不限）。 */
function withFilters(sp: URLSearchParams, f: CaseFilters): string {
  if (f.source) sp.set("source", f.source);
  if (f.field) sp.set("field", f.field);
  if (f.crime) sp.set("crime", f.crime);
  if (f.year) sp.set("year", f.year);
  if (f.viewed) sp.set("viewed", f.viewed);
  return sp.toString();
}

/** 只写非空值，保持 URL 干净。 */
function buildParams(values: Record<string, string>): string {
  const sp = new URLSearchParams();
  Object.entries(values).forEach(([k, v]) => { if (v) sp.set(k, v); });
  return sp.toString();
}

function asSort(value: string | null): CaseSort {
  return SORTS.includes(value as CaseSort) ? (value as CaseSort) : DEFAULT_CASE_SORT;
}

function asViewed(value: string | null): CaseViewedFilter {
  return value === "no" || value === "yes" ? value : "";
}
