"use client";
import type { StatuteHit } from "@/lib/statuteTypes";

/** 条文全文检索结果：法名 · 条号 · 片段（命中词高亮）。 */
export default function StatuteSearchResults({
  query, hits, loading, onPick,
}: {
  query: string;
  hits: StatuteHit[];
  loading: boolean;
  onPick: (law: string, no: number) => void;
}) {
  if (loading) return <p className="muted">检索中…</p>;
  if (!query.trim()) return <p className="muted">输入关键词检索全部法条正文。</p>;
  if (hits.length === 0) return <p className="muted">没有命中「{query}」。</p>;
  return (
    <div>
      <p className="muted">命中 {hits.length} 条</p>
      <div className="statute-list">
        {hits.map((hit) => (
          <button
            key={`${hit.law}-${hit.no}-${hit.sub}`}
            className="statute-row statute-row-col"
            onClick={() => onPick(hit.law, hit.no)}
          >
            <span className="statute-hit-head">
              {hit.law_name} · {hit.label}
            </span>
            <span className="statute-hit-body">{highlight(hit.snippet, query)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** 把命中词包成 <mark>；无命中则原样返回。 */
function highlight(text: string, query: string) {
  const kw = query.trim();
  if (!kw) return text;
  const idx = text.indexOf(kw);
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="statute-mark">{kw}</mark>
      {text.slice(idx + kw.length)}
    </>
  );
}
