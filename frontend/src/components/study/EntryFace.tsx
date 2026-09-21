"use client";
import type { CaseRef, Entry } from "@/lib/types";
import StudyCardShell, { type RateResult } from "./StudyCardShell";

interface Props {
  entry: Entry;
  flipped: boolean;
  onFlip: () => void;
  isMarked: boolean;
  reviewedToday: boolean;
  aiLabel: string;
  submitting: boolean;
  onRate: (result: RateResult) => void;
  onAskAi: () => void;
  onToggleMark: () => void;
  onEdit: () => void;
  onStatute: (statute: string) => void;
  onCase: (c: CaseRef) => void;
}

/** 条目卡正/背面（2426 条 entries 的原样式，仅搬到共用外壳里）。 */
export default function EntryFace({
  entry, flipped, onFlip, isMarked, reviewedToday, aiLabel, submitting,
  onRate, onAskAi, onToggleMark, onEdit, onStatute, onCase,
}: Props) {
  return (
    <StudyCardShell
      flipped={flipped}
      onFlip={onFlip}
      submitting={submitting}
      onRate={onRate}
      tag={`${entry.subject} · ${entry.submodule}`}
      title={entry.point}
      frontHint="点卡片看结论"
      frontBody={<p>{entry.anchor}</p>}
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
          <span className="priority-badge">{entry.priority}</span>
          <h3>{entry.conclusion}</h3>
          {entry.note && <p className="note">⚠ {entry.note}</p>}
          {entry.statutes.length > 0 && (
            <div className="source-chips">
              {entry.statutes.map((st, i) => (
                <button key={i} className="chip"
                  onClick={(e) => { e.stopPropagation(); onStatute(st); }}>{st}</button>
              ))}
            </div>
          )}
          {entry.cases.length > 0 && (
            <div className="source-chips">
              {entry.cases.map((c, i) => (
                <button key={i} className="chip-case"
                  onClick={(e) => { e.stopPropagation(); onCase(c); }}>
                  {c.title || `案例 ${i + 1}`}
                </button>
              ))}
            </div>
          )}
          <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onAskAi(); }}>
            问 AI{aiLabel}
          </button>
          <button className="btn btn-ghost"
            onClick={(e) => { e.stopPropagation(); onToggleMark(); }}>
            {isMarked ? "已标记 ✓" : "标记"}
          </button>
          <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); onEdit(); }}>
            编辑
          </button>
        </>
      )}
    />
  );
}
