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

export type CaseSort = "relevance" | "newest" | "oldest";

/** 检索/浏览的筛选条件（空串 = 不限）。 */
export interface CaseFilters {
  source: string;
  field: string;
  crime: string;
  year: string;
  sort: CaseSort;
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
