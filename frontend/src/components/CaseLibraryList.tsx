"use client";
import type { CaseHit } from "@/lib/caseLibTypes";

/** 案例命中列表：来源·类别·案号·日期 + 正文片段（命中词高亮）。 */
export default function CaseLibraryList({
  hits, query, loading, onPick,
}: {
  hits: CaseHit[];
  query: string;
  loading: boolean;
  onPick: (hit: CaseHit) => void;
}) {
  if (loading) return <p className="muted">检索中…</p>;
  if (!query.trim()) return <p className="muted">输入关键词检索案例，如「房屋租赁」「正当防卫」。</p>;
  if (hits.length === 0) return <p className="muted">没有命中「{query}」。</p>;
  return (
    <div>
      <p className="muted">命中 {hits.length} 篇</p>
      <div className="statute-list">
        {hits.map((hit) => (
          <button key={`${hit.source}-${hit.loc}`}
            className="statute-row statute-row-col"
            onClick={() => onPick(hit)}>
            <span className="caselib-hit-title">{highlight(hit.title, query)}</span>
            <span className="muted">
              {[hit.source, hit.category, hit.case_no, hit.date]
                .filter(Boolean).join(" · ")}
            </span>
            <span className="statute-hit-body">{highlight(hit.snippet, query)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** 把命中词包成 <mark>；多关键词时逐个高亮。 */
function highlight(text: string, query: string) {
  const terms = query.split(/[\s、，,]+/).filter(Boolean).map(escape);
  if (terms.length === 0) return text;
  const parts = text.split(new RegExp(`(${terms.join("|")})`, "g"));
  return (
    <>
      {parts.map((part, i) => (i % 2 === 1
        ? <mark key={i} className="statute-mark">{part}</mark>
        : part))}
    </>
  );
}

function escape(term: string) {
  return term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
