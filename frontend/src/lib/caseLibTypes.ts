/** 案例库检索与阅读（对应后端 /api/case/*）。 */

export interface CaseHit {
  source: string;
  loc: string;
  title: string;
  category: string;
  case_no: string;
  keywords: string[];
  date: string;
  url: string;
  snippet: string;
  score: number;
  /** 是否已看过（服务端 case_views 打点） */
  viewed: boolean;
}

/** 文书小节：label 为空表示无标题正文段。 */
export interface CaseSection {
  label: string;
  text: string;
}

export interface CaseDetail {
  source: string;
  loc: string;
  title: string;
  category: string;
  case_no: string;
  keywords: string[];
  date: string;
  url: string;
  sections: CaseSection[];
  /** 展示时自动合并掉的重复段/句数量 */
  paragraphs_dropped: number;
}

export interface CaseStats {
  total: number;
  sources: { source: string; n: number }[];
}

/** 分面取值（部门法/罪名/年份/来源库通用结构）。 */
export interface CaseFacet {
  value: string;
  n: number;
}

export interface CaseFacets {
  total: number;
  scanned: number;
  fields: CaseFacet[];
  crimes: CaseFacet[];
  years: CaseFacet[];
  sources: CaseFacet[];
}

/** 排序：未看过优先（默认）/ 相关度 / 最新 / 最早 */
export type CaseSort = "unviewed" | "relevance" | "newest" | "oldest";

/** 案例库默认阅读顺序：未看过的排在前面 */
export const DEFAULT_CASE_SORT: CaseSort = "unviewed";

/** 阅读状态筛选：全部 / 只看未看过 / 只看已看过 */
export type CaseViewedFilter = "" | "no" | "yes";

/** 检索/浏览的筛选条件（空串 = 不限）。 */
export interface CaseFilters {
  source: string;
  field: string;
  crime: string;
  year: string;
  viewed: CaseViewedFilter;
  sort: CaseSort;
}

/** 阅读视图的前后篇（导航按钮只用到基本元信息）。 */
export interface CaseNeighborItem {
  source: string;
  loc: string;
  title: string;
  category: string;
  case_no: string;
  date: string;
}

export interface CaseNeighbors {
  prev: CaseNeighborItem | null;
  next: CaseNeighborItem | null;
  /** 当前篇在全库命中顺序里的下标；-1 = 当前上下文里没有这篇 */
  index: number;
  total: number;
}

/** 「看过」打点结果（POST /api/case/view）。 */
export interface CaseViewRecord {
  source: string;
  loc: string;
  views: number;
  first_time: boolean;
  first_viewed_at: string;
  last_viewed_at: string;
}

/** 阅读历史条目（GET /api/case/history）。 */
export interface CaseHistoryItem extends CaseNeighborItem {
  url: string;
  views: number;
  first_viewed_at: string;
  last_viewed_at: string;
}

export interface CaseHistoryResult {
  items: CaseHistoryItem[];
  total: number;
}

export interface CaseSearchResult {
  items: CaseHit[];
  total: number;
  offset: number;
  limit: number;
  sort: CaseSort;
  query: string;
  filters: Omit<CaseFilters, "sort">;
}
