"use client";
import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import type { Entry, Plan } from "@/lib/types";
import SourceViewer, { type SourceTarget } from "./SourceViewer";

export default function FlashcardView() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(0);
  const [error, setError] = useState("");
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [statute, setStatute] = useState<string | null>(null);
  const startRef = useRef(Date.now());

  useEffect(() => {
    getJson<Plan>("/api/plans/today")
      .then(setPlan)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!plan) return <p className="muted">加载中…</p>;

  const items = plan.items;
  if (items.length === 0) {
    return <div className="card"><p>今日没有条目，请先到「我的」导入数据。</p></div>;
  }
  if (index >= items.length) {
    return (
      <div className="card center">
        <h2>今日卡片已看完</h2>
        <p className="muted">共 {items.length} 张，已记录自评。</p>
      </div>
    );
  }

  const entry: Entry = items[index];

  async function rate(result: "good" | "fuzzy" | "bad") {
    const duration = Math.round((Date.now() - startRef.current) / 1000);
    await postJson("/api/reviews", {
      entry_id: entry.id, mode: "read", result, duration_sec: duration,
    });
    startRef.current = Date.now();
    setFlipped(false);
    setDone((d) => d + 1);
    setIndex((i) => i + 1);
  }

  function askAi() {
    window.dispatchEvent(new CustomEvent("ask-ai", {
      detail: { entry_id: entry.id, question: `讲解「${entry.point}」的要点和易错点` },
    }));
  }

  return (
    <div>
      <p className="muted">{index + 1} / {items.length} · 完成 {done} 张</p>
      <div className={`flashcard${flipped ? " flipped" : ""}`} onClick={() => setFlipped((f) => !f)}>
        <div className="flashcard-inner">
          <div className="flashcard-face">
            <span className="tag">{entry.subject} · {entry.submodule}</span>
            <h2>{entry.point}</h2>
            <p>{entry.anchor}</p>
            <p className="hint">点卡片看结论</p>
          </div>
          <div className="flashcard-face back">
            <span className="priority-badge">{entry.priority}</span>
            <h3>{entry.conclusion}</h3>
            {entry.note && <p className="note">⚠ {entry.note}</p>}
            {entry.statutes.length > 0 && (
              <div className="source-chips">
                {entry.statutes.map((st, i) => (
                  <button
                    key={i}
                    className="chip"
                    onClick={(e) => {
                      e.stopPropagation();
                      setStatute(st);
                    }}
                  >
                    {st}
                  </button>
                ))}
              </div>
            )}
            {entry.cases.length > 0 && (
              <div className="source-chips">
                {entry.cases.map((c, i) => (
                  <button
                    key={i}
                    className="chip"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSource({ kind: "case", ref: c.source, loc: c.loc });
                    }}
                  >
                    {c.title || `案例 ${i + 1}`}
                  </button>
                ))}
              </div>
            )}
            <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); askAi(); }}>
              问 AI
            </button>
          </div>
        </div>
      </div>
      {flipped && (
        <div className="rate-row">
          <button className="btn btn-bad" onClick={() => rate("bad")}>没记住</button>
          <button className="btn btn-ghost" onClick={() => rate("fuzzy")}>模糊</button>
          <button className="btn btn-good" onClick={() => rate("good")}>记住了</button>
        </div>
      )}
      <SourceViewer
        source={source}
        statute={statute}
        onClose={() => { setSource(null); setStatute(null); }}
      />
    </div>
  );
}
