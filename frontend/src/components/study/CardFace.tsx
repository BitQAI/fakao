"use client";
import { mdToHtml } from "@/lib/md";
import type { Entry } from "@/lib/types";
import StudyCardShell, { type RateResult } from "./StudyCardShell";

interface Props {
  entry: Entry;                       // kind === "card" 的卡片条目
  flipped: boolean;
  onFlip: () => void;
  isMarked: boolean;
  reviewedToday: boolean;
  aiLabel: string;
  submitting: boolean;
  onRate: (result: RateResult) => void;
  onAskAi: () => void;
  onToggleMark: () => void;
  onStatute: (statute: string) => void;
}

/** 法条题卡的正/背面：与条目卡同一外壳，只有内容区不同。 */
export default function CardFace({
  entry, flipped, onFlip, isMarked, reviewedToday, aiLabel, submitting,
  onRate, onAskAi, onToggleMark, onStatute,
}: Props) {
  const options = entry.options ?? [];
  const basis = entry.statutes[0] ?? entry.submodule;
  return (
    <StudyCardShell
      flipped={flipped}
      onFlip={onFlip}
      submitting={submitting}
      onRate={onRate}
      tag={`${entry.subject} · ${entry.submodule}`}
      title={entry.anchor}
      frontHint="点卡片看答案"
      frontBody={options.length > 0 ? (
        <div className="options-col">
          {options.map((opt) => <span key={opt} className="option">{opt}</span>)}
        </div>
      ) : undefined}
      badges={(
        <>
          {isMarked && <span className="badge">已标记</span>}
          {(entry.reviewed_today || reviewedToday) && <span className="badge">今日已看</span>}
          {entry.read_count
            ? <span className="badge">已看 {entry.read_count} 次</span>
            : <span className="badge">未看</span>}
        </>
      )}
      back={(
        <>
          <span className="priority-badge">{options.length > 0 ? "选择题" : "填空题"}</span>
          <h3>正确答案：{entry.conclusion}</h3>
          {entry.rationale && (
            <div className="analysis"
              dangerouslySetInnerHTML={{ __html: mdToHtml(entry.rationale) }} />
          )}
          {entry.article_text && <p className="note">条文：{entry.article_text}</p>}
          <div className="source-chips">
            <button className="chip"
              onClick={(e) => { e.stopPropagation(); onStatute(basis); }}>{basis}</button>
          </div>
          <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onAskAi(); }}>
            问 AI{aiLabel}
          </button>
          <button className="btn btn-ghost"
            onClick={(e) => { e.stopPropagation(); onToggleMark(); }}>
            {isMarked ? "已标记 ✓" : "标记"}
          </button>
        </>
      )}
    />
  );
}
