"use client";
import type { StatuteLaw } from "@/lib/statuteTypes";

/** 法条库列表：纯列表，筛选由页面级搜索框统一负责。 */
export default function StatuteList({
  laws, loading, onPick,
}: {
  laws: StatuteLaw[];
  loading: boolean;
  onPick: (key: string) => void;
}) {
  return (
    <div>
      {loading && <p className="muted">加载中…</p>}
      <div className="statute-list">
        {laws.map((law) => (
          <button key={law.key} className="statute-row" onClick={() => onPick(law.key)}>
            <span className="statute-row-name">{law.name}</span>
            <span className="muted">{law.articles} 条</span>
          </button>
        ))}
      </div>
    </div>
  );
}
