"use client";
import type { CaseHit } from "@/lib/caseLibTypes";

/** 案例命中列表：来源·类别·案号·日期 + 正文片段（命中词高亮）。 */
export default function CaseLibraryList({
  hits, query, loading, total, summary, onPick, onLoadMore,
}: {
  hits: CaseHit[];
  query: string;
  loading: boolean;
  total: number;
  summary?: string;
  onPick: (hit: CaseHit) => void;
  onLoadMore: () => void;
}) {
  if (loading && hits.length === 0) return <p className="muted">检索中…</p>;
  if (hits.length === 0) {
    return <p className="muted">
      {query.trim() ? `没有命中「${query}」，换个词或清空筛选试试。`
                    : "没有符合当前筛选条件的案例。"}
    </p>;
  }
  const remain = total - hits.length;
  return (
    <div>
      <p className="muted caselib-count">
        共 {total} 篇（已显示 {hits.length}）
        {summary && <span className="caselib-summary">｜{summary}</span>}
      </p>
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
      {remain > 0 && (
        <button className="btn caselib-more" onClick={onLoadMore} disabled={loading}>
          {loading ? "加载中…" : `加载更多（还有 ${remain} 篇）`}
        </button>
      )}
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
