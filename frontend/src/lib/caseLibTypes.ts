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
