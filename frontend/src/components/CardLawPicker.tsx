"use client";
import { useState } from "react";
import type { CardCoverage } from "@/lib/types";

interface Props {
  coverage: CardCoverage;
  laws: Set<string>;
  onToggle: (law: string) => void;
  keyword: string;
}

/** 按法条题卡选择：科目 → 法条主名（题卡的 submodule）多选。 */
export default function CardLawPicker({ coverage, laws, onToggle, keyword }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const kw = keyword.trim();
  const subjects = Object.keys(coverage).filter((s) => !kw || s.includes(kw));
  const total = Object.values(coverage).reduce(
    (n, lawMap) => n + Object.values(lawMap).reduce((m, v) => m + v.count, 0), 0);
  if (subjects.length === 0) {
    return <p className="muted search-empty">无匹配科目</p>;
  }
  return (
    <div className="pick-tree" data-testid="card-law-picker">
      <p className="muted">
        共 {total} 张法条题卡（客观题）。勾选科目或具体法条即可只刷题卡。
      </p>
      {subjects.map((subject) => {
        const lawMap = coverage[subject];
        const entries = Object.entries(lawMap)
          .filter(([law]) => !kw || law.includes(kw) || subject.includes(kw));
        if (entries.length === 0) return null;
        const count = entries.reduce((n, [, v]) => n + v.count, 0);
        const picked = entries.filter(([law]) => laws.has(law)).length;
        const open = expanded.has(subject) || Boolean(kw);
        return (
          <div key={subject} className="pick-group">
            <div className="pick-row pick-subject-row">
              <input
                type="checkbox"
                checked={picked === entries.length}
                onChange={() => {
                  entries.forEach(([law]) => {
                    const all = picked === entries.length;
                    if (all === laws.has(law)) onToggle(law);
                  });
                }}
              />
              <button className="pick-toggle"
                onClick={() => setExpanded((prev) => {
                  const next = new Set(prev);
                  if (next.has(subject)) next.delete(subject);
                  else next.add(subject);
                  return next;
                })}>
                {open ? "▾" : "▸"} {subject}
                <span className="muted">（{count} 张 · 已选 {picked} 部法）</span>
              </button>
            </div>
            {open && (
              <div className="pick-points">
                {entries.map(([law, meta]) => (
                  <label key={law} className="pick-point">
                    <input type="checkbox" checked={laws.has(law)}
                      onChange={() => onToggle(law)} />
                    <span className="pick-point-name">{law}</span>
                    <span className="pick-state st-new">{meta.count} 张</span>
                    {meta.unread > 0 && <span className="pick-state st-unread">未看 {meta.unread}</span>}
                  </label>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
