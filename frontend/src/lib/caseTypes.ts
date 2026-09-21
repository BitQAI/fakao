export type CaseQType = "case" | "essay" | "composite";

export interface CaseMaterial {
  label: string;
  text: string;
}

/** 题型形式要求（后端 subjective_templates.SPECS 下发） */
export interface CaseSpec {
  label: string;
  min_chars?: number;
  advise_chars?: number;
  paragraphs?: string;
  min_questions?: number;
  max_questions?: number;
}

export interface EssayMetrics {
  chars: number;
  min_chars: number;
  advise_chars: number;
  reach: boolean;
  copy_ratio: number;
  copy_limit: number;
  copied: boolean;
  verdict: string[];
}

export interface CasePoint {
  no: number;
  kind: string;
  text: string;
  statutes: string[];
  verified?: boolean;
  /** 归属第几小问（综合大案例一题多问） */
  qno?: number;
}

export interface ExamSlot {
  slot: number;
  label: string;
  score: number;
  minutes: number;
}

export interface CaseQuestion {
  id: number;
  subject: string;
  stem: string;
  questions: string[];
  case?: { title: string; case_no: string; category: string } | null;
  qtype?: CaseQType;
  materials?: CaseMaterial[];
  spec?: CaseSpec;
  slot?: ExamSlot;
  skeleton?: string[];
}

export interface CaseDetail extends CaseQuestion {
  points: CasePoint[];
  reference: string;
}

export interface CaseMissed {
  no: number;
  kind: string;
  text: string;
  statutes: string[];
  qno?: number;
  links: { ref: string; law: string; no: number; url: string }[];
}

export interface KindStat {
  kind: string;
  hit: number;
  total: number;
}

export interface CaseGrade {
  score: number;
  hit: number[];
  total: number;
  missed: CaseMissed[];
  reference: string;
  by_kind: KindStat[];
  essay?: EssayMetrics | null;
}

export interface CaseMissItem {
  text: string;
  kind: string;
  statutes: string[];
  subject: string;
  asked: number;
  missed: number;
  last_missed: string | null;
  question_ids: number[];
  links: { ref: string; law: string; no: number; url: string }[];
}

export interface CaseAttempt {
  id: number;
  question_id: number;
  ts: string;
  mode: string;
  subject: string;
  stem: string;
  score: number;
  hit: number[];
  total: number;
  missed: string[];
}

export interface CaseStats {
  attempts: number;
  questions_done: number;
  published: number;
  by_subject: { subject: string; n: number; avg: number }[];
}
