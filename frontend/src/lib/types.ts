export interface Source {
  type: string;
  ref: string;
  loc: string;
}

export interface CaseRef {
  source: string;
  loc: string;
  title?: string;
}

export interface Entry {
  id: string;
  subject: string;
  submodule: string;
  point: string;
  anchor: string;
  conclusion: string;
  priority: string;
  rationale: string;
  sources: Source[];
  cases: CaseRef[];
  statutes: string[];
  note: string | null;
  tts_text: string;
  bucket?: "retry" | "review" | "new";
  read_count?: number;
  listen_count?: number;
  last_ts?: string | null;
  reviewed_today?: boolean;
  listened_today?: boolean;
}

export interface Plan {
  date: string;
  quota: number;
  rationale: string;
  items: Entry[];
  counts: { retry: number; review: number; new: number };
  /** 看背用的法条题卡（每 3 张留 1 张，未看过优先） */
  statute_cards?: StatuteCard[];
}

/** 法条卡：一条法条 + 基于它命制的题（法条驱动题在四个入口共用） */
export interface StatuteCard {
  kind: "statute";
  quiz_id: number;
  subject: string;
  qtype: "choice" | "cloze" | "judge";
  stem: string;
  options: string[];
  answer: string;
  analysis: string;
  basis: string;
  law_key: string;
  no: number;
  sub: number;
  article_text: string;
  unseen?: boolean;
}

export interface Stats {
  date: string;
  done: number;
  quota: number;
  percent: number;
  over_done: boolean;
  quiz_total: number;
  quiz_correct: number;
  listen_min: number;
  counts: { retry: number; review: number; new: number };
  weak: string;
}

export interface Report {
  id: number;
  date: string;
  kind: string;
  content: string;
  created_at: string;
}

export interface TodayPayload {
  date: string;
  days_left: number | null;
  plan: Plan;
  stats: Stats;
  streak: { current: number; longest: number };
}

export interface ListenPayload {
  items: Entry[];
  remaining: number;
  generating: boolean;
  custom?: boolean;
  heard_total?: number;
  /** 听学用的法条题卡（每 3 段留 1 段，音频按需合成） */
  statute_cards?: StatuteCard[];
}

export interface HistoryItem {
  id: number;
  entry_id: string;
  ts: string;
  mode: "read" | "listen";
  result: string;
  duration_sec: number;
  entry: {
    id: string;
    subject: string;
    submodule: string;
    point: string;
    anchor: string;
    conclusion: string;
    priority: string;
  };
}

export interface LeaderboardItem {
  entry_id: string;
  subject: string;
  submodule: string;
  point: string;
  anchor: string;
  conclusion: string;
  priority: string;
  read_count: number;
  listen_count: number;
  total_count: number;
  read_repeat: number;
  listen_repeat: number;
  last_ts: string | null;
}

export interface MarkItem {
  id: number;
  entry_id: string;
  created_at: string;
  entry: Entry;
}

export interface WrongbookItem {
  id: string;
  subject: string;
  submodule: string;
  point: string;
  anchor: string;
  conclusion: string;
  priority: string;
  quiz_wrong_count: number;
  bad_count: number;
  wrong_count: number;
  last_wrong_ts: string | null;
}

export interface DailyStat {
  date: string;
  read: number;
  listen: number;
  quiz: number;
}

export interface StatsOverview {
  days: number;
  daily: DailyStat[];
  totals: { read: number; listen: number; quiz: number; minutes: number };
  mastery: Record<string, number>;
  streak: { current: number; longest: number };
}

export interface QuizQuestion {
  id: number;
  entry_id: string | null;
  qtype: "choice" | "cloze" | "judge";
  stem: string;
  options: string[];
  answer: string;
  analysis?: string;
  /** 法条依据（题库题专用，如「刑诉法91条」） */
  basis?: string;
  subject?: string;
  point?: string;
}

export interface QuizHistoryItem {
  answer_id: number;
  quiz_id: number;
  ts: string;
  user_answer: string;
  picked_texts: string[];
  correct: boolean;
  qtype: "choice" | "cloze" | "judge";
  stem: string;
  options: string[];
  answer: string;
  analysis: string;
  basis?: string;
}

export interface CoveragePoint {
  state: string;
  unread: number;
  unlistened: number;
}

export interface CoverageNode {
  count: number;
  states: Record<string, number>;
  unread: number;
  unlistened: number;
  submodules: Record<string, {
    count: number;
    states: Record<string, number>;
    unread: number;
    unlistened: number;
    points: Record<string, CoveragePoint>;
  }>;
}

export type CoverageTree = Record<string, CoverageNode>;
