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
}

export interface Plan {
  date: string;
  quota: number;
  rationale: string;
  items: Entry[];
  counts: { retry: number; review: number; new: number };
}

export interface Stats {
  date: string;
  done: number;
  quota: number;
  percent: number;
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
  morning_report: Report | null;
}

export interface ListenPayload {
  items: Entry[];
  remaining: number;
  generating: boolean;
  custom?: boolean;
  heard_total?: number;
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

export interface QuizQuestion {
  id: number;
  entry_id: string;
  qtype: "choice" | "cloze";
  stem: string;
  options: string[];
  answer: string;
  analysis?: string;
}

export interface QuizHistoryItem {
  answer_id: number;
  quiz_id: number;
  ts: string;
  user_answer: string;
  picked_texts: string[];
  correct: boolean;
  qtype: "choice" | "cloze";
  stem: string;
  options: string[];
  answer: string;
  analysis: string;
}

export interface CoverageNode {
  count: number;
  states: Record<string, number>;
  submodules: Record<string, {
    count: number;
    states: Record<string, number>;
    points: Record<string, string>;
  }>;
}

export type CoverageTree = Record<string, CoverageNode>;
