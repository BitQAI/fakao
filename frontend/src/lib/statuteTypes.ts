export interface StatuteLaw {
  key: string;
  name: string;
  articles: number;
  meta: Record<string, string>;
}

export interface StatuteArticle {
  no: number;
  sub: number;
  label: string;
  text: string;
  chapter: string[];
}

export interface StatuteLawPayload {
  key: string;
  name: string;
  meta: Record<string, string>;
  total: number;
  offset: number;
  chapters: string[];
  items: StatuteArticle[];
}

export interface StatuteHit {
  law: string;
  law_name: string;
  no: number;
  sub: number;
  label: string;
  snippet: string;
  chapter: string[];
}

export interface StatuteEntryRef {
  id: string;
  subject: string;
  submodule: string;
  point: string;
  priority: string;
}
