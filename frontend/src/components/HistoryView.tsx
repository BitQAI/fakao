"use client";
import { useEffect, useState } from "react";
import { getJson } from "@/lib/api";
import type { HistoryItem } from "@/lib/types";

const MODE_LABEL: Record<string, string> = { read: "看背", listen: "听学" };
const RESULT_LABEL: Record<string, string> = {
  good: "记住了", fuzzy: "模糊", bad: "没记住", exposed: "已听",
};

export default function HistoryView() {
  const [mode, setMode] = useState<"all" | "read" | "listen">("all");
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setItems(null);
    const q = mode === "all" ? "" : `&mode=${mode}`;
    getJson<{ items: HistoryItem[] }>(`/api/reviews/history?limit=200${q}`)
      .then((d) => setItems(d.items))
      .catch((e) => setError(String(e)));
  }, [mode]);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!items) return <p className="muted">加载中…</p>;
  if (items.length === 0) {
    return (
      <div className="card">
        <p className="muted">还没有学习记录，先去「学习」页看几页、听几段吧。</p>
      </div>
    );
  }

  const groups: { date: string; items: HistoryItem[] }[] = [];
  for (const it of items) {
    const day = it.ts.slice(0, 10);
    const last = groups[groups.length - 1];
    if (last && last.date === day) last.items.push(it);
    else groups.push({ date: day, items: [it] });
  }

  return (
    <div className="page-box">
      <div className="segments">
        {([["all", "全部"], ["read", "看背"], ["listen", "听学"]] as const).map(([k, label]) => (
          <button key={k} className={`segment${mode === k ? " active" : ""}`}
            onClick={() => setMode(k)}>
            {label}
          </button>
        ))}
      </div>
      {groups.map((g) => (
        <section key={g.date}>
          <p className="muted" style={{ margin: "8px 0" }}>
            {g.date} · {g.items.length} 条
          </p>
          {g.items.map((it) => (
            <div className="card history-card" key={it.id}>
              <div className="history-head">
                <span className="badge">{MODE_LABEL[it.mode] ?? it.mode}</span>
                <span className="muted">
                  {it.ts.slice(11, 16)} · {RESULT_LABEL[it.result] ?? it.result}
                  {it.duration_sec > 0 ? ` · ${it.duration_sec}s` : ""}
                </span>
              </div>
              <p className="history-stem">{it.entry.subject} · {it.entry.point}</p>
              <div className="row">
                <a className="btn" href={`/study?view=read&entry=${it.entry_id}`}>再看</a>
                <a className="btn" href={`/study?view=listen&entry=${it.entry_id}`}>再听</a>
              </div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
