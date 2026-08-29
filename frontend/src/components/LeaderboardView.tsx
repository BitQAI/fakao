"use client";
import { useEffect, useState } from "react";
import { getJson } from "@/lib/api";
import type { LeaderboardItem } from "@/lib/types";

type SortKey = "total" | "read" | "listen";

export default function LeaderboardView() {
  const [sort, setSort] = useState<SortKey>("total");
  const [items, setItems] = useState<LeaderboardItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setItems(null);
    getJson<{ items: LeaderboardItem[] }>(`/api/leaderboard?limit=200&sort=${sort}`)
      .then((d) => setItems(d.items))
      .catch((e) => setError(String(e)));
  }, [sort]);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!items) return <p className="muted">加载中…</p>;
  if (items.length === 0) {
    return (
      <div className="card">
        <p className="muted">暂无排行数据，先在「学习」页看几页、听几段吧。</p>
      </div>
    );
  }

  return (
    <div className="page-box">
      <div className="segments">
        {([["total", "看+听"], ["read", "只看"], ["listen", "只听"]] as [SortKey, string][]).map(
          ([k, label]) => (
            <button key={k} className={`segment${sort === k ? " active" : ""}`}
              onClick={() => setSort(k)}>
              {label}
            </button>
          ),
        )}
      </div>
      <p className="muted">按总次数排序，重复次数 = 累计次数 − 首次。</p>
      {items.map((it, i) => (
        <div className="card" key={it.entry_id} style={{ padding: "12px 14px" }}>
          <div className="history-head">
            <span className="badge">#{i + 1}</span>
            <span className="muted">{it.last_ts ? it.last_ts.slice(0, 10) : ""}</span>
          </div>
          <p className="history-stem">{it.subject} · {it.point}</p>
          <p className="muted">
            合计 {it.total_count} 次 · 看 {it.read_count}（重复 {it.read_repeat}）
            · 听 {it.listen_count}（重复 {it.listen_repeat}）
          </p>
          <p className="muted">{it.anchor}</p>
          <div className="row">
            <a className="btn" href={`/study?view=read&entry=${it.entry_id}`}>继续看</a>
            <a className="btn" href={`/study?view=listen&entry=${it.entry_id}`}>继续听</a>
          </div>
        </div>
      ))}
    </div>
  );
}
