"use client";
import { useCallback, useEffect, useState } from "react";
import { getJson } from "@/lib/api";
import type { CaseMissItem } from "@/lib/caseTypes";

/** 复盘池：按采分点聚合未命中情况——反复踩同一个点才是真薄弱。 */
export default function CaseReview() {
  const [items, setItems] = useState<CaseMissItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [subject, setSubject] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    const url = subject
      ? `/api/cases/misses?subject=${encodeURIComponent(subject)}`
      : "/api/cases/misses";
    getJson<{ items: CaseMissItem[] }>(url)
      .then((d) => setItems(d.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [subject]);

  useEffect(load, [load]);

  const subjects = Array.from(new Set(items.map((i) => i.subject)));

  if (loading) return <p className="muted">加载中…</p>;
  if (items.length === 0) {
    return (
      <p className="muted">
        复盘池是空的——要么没有未命中的采分点，要么还没做过案例题。
      </p>
    );
  }
  return (
    <div className="case-review">
      <div className="mode-row">
        <button className={`mode-btn${subject === "" ? " active" : ""}`}
          onClick={() => setSubject("")}>全部</button>
        {subjects.map((s) => (
          <button key={s} className={`mode-btn${subject === s ? " active" : ""}`}
            onClick={() => setSubject(s)}>{s}</button>
        ))}
      </div>
      <p className="muted">共 {items.length} 个薄弱采分点，按未命中次数排序</p>
      {items.map((it) => (
        <div key={it.text} className="card case-miss-card">
          <div className="case-head">
            <span className="kind-badge">{it.kind || "其他"}</span>
            <span className="priority-badge">{it.subject}</span>
            <span className="muted">未命中 {it.missed}/{it.asked} 次</span>
          </div>
          <p>{it.text}</p>
          {it.links.length > 0 && (
            <div className="statute-refs">
              {it.links.map((l) => (
                <button key={l.ref} className="chip"
                  onClick={() => { window.location.href = l.url; }}>
                  看依据：{l.ref}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
