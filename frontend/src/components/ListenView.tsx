"use client";
import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import type { Plan } from "@/lib/types";
import SourceViewer, { type SourceTarget } from "./SourceViewer";

export default function ListenView() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState<SourceTarget | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const durRef = useRef(0);

  useEffect(() => {
    getJson<Plan>("/api/plans/today")
      .then(setPlan)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!plan) return <p className="muted">加载中…</p>;

  const items = plan.items.filter((e) => e.tts_text);
  if (items.length === 0) return <div className="card"><p>今日没有可听的条目。</p></div>;

  const entry = items[idx];

  function next() {
    if (idx + 1 < items.length) setIdx(idx + 1);
    else { setIdx(0); setPlaying(false); }
  }

  return (
    <div className="page-box">
      <div className="card center">
        <h2>{entry.subject} · {entry.point}</h2>
        <p className="muted">{idx + 1} / {items.length} · 听学只记暴露，不记掌握</p>
        <audio
          ref={audioRef}
          controls
          autoPlay
          src={`/api/audio/${entry.id}`}
          onLoadedMetadata={(e) => { durRef.current = Math.round(e.currentTarget.duration || 0); }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => {
            void postJson("/api/reviews", {
              entry_id: entry.id, mode: "listen", result: "exposed",
              duration_sec: durRef.current,
            });
            next();
          }}
          onError={() => setError("音频生成中或不可用，请稍后重试")}
        />
        <div className="row">
          <button className="btn btn-ghost" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>上一个</button>
          <button className="btn btn-ghost" onClick={next}>{playing ? "跳过" : "下一段"}</button>
        </div>
        {entry.cases.length > 0 && (
          <div className="source-chips" style={{ justifyContent: "center" }}>
            {entry.cases.map((c, i) => (
              <button
                key={i}
                className="chip"
                onClick={() => setSource({ kind: "case", ref: c.source, loc: c.loc })}
              >
                查看原文 · 案例 {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>
      <SourceViewer source={source} onClose={() => setSource(null)} />
    </div>
  );
}
