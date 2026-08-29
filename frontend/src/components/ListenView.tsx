"use client";
import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import type { Entry, ListenPayload } from "@/lib/types";
import SourceViewer, { type SourceTarget } from "./SourceViewer";

export default function ListenView() {
  const [queue, setQueue] = useState<ListenPayload | null>(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [moreCount, setMoreCount] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [source, setSource] = useState<SourceTarget | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const durRef = useRef(0);

  useEffect(() => {
    getJson<ListenPayload>("/api/listen")
      .then(setQueue)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!queue) return <p className="muted">加载中…</p>;

  const items = queue.items;
  if (items.length === 0) {
    return (
      <div className="card">
        <p>{queue.generating ? "正在生成更多听学内容…" : "暂无听学内容。"}</p>
        {queue.remaining === 0 && <p className="muted">剩余不足时系统会自动续批生成。</p>}
      </div>
    );
  }

  const entry: Entry = items[idx];

  if (idx >= items.length) {
    return (
      <div className="page-box">
        <div className="card center">
          <h2>本轮听学完成</h2>
          <p className="muted">共听了 {items.length} 段 · 剩余可听 {queue.remaining}</p>
          <div className="continue-box">
            <p className="muted">继续听？选择数量：</p>
            <div className="row">
              <button className="btn" disabled={loadingMore}
                onClick={() => void loadMore(5)}>再听 5 段</button>
              <button className="btn" disabled={loadingMore}
                onClick={() => void loadMore(10)}>再听 10 段</button>
            </div>
            <div className="continue-custom">
              <input
                type="number" min={1} max={50} placeholder="自定义数量"
                value={moreCount}
                onChange={(e) => setMoreCount(e.target.value)}
              />
              <button className="btn btn-primary" disabled={loadingMore || !moreCount}
                onClick={() => void loadMore(Number(moreCount))}>继续</button>
            </div>
            {notice && <p className="muted">{notice}</p>}
          </div>
        </div>
        <SourceViewer source={source} onClose={() => setSource(null)} />
      </div>
    );
  }

  async function loadMore(count: number) {
    if (count < 1 || count > 50) return;
    setLoadingMore(true);
    setNotice("");
    try {
      const r = await postJson<ListenPayload>("/api/listen/more", {
        count,
        exclude: items.map((i) => i.id),
      });
      if (!r.items.length) {
        setNotice("没有更多听学内容了。");
        return;
      }
      setQueue((q) => (q ? { ...q, items: [...q.items, ...r.items], remaining: r.remaining } : q));
      setIdx(items.length);
      setPlaying(false);
    } catch (e) {
      setNotice("加载失败：" + String(e));
    } finally {
      setLoadingMore(false);
      setMoreCount("");
    }
  }

  function next() {
    if (idx + 1 < items.length) setIdx(idx + 1);
    else { setIdx(items.length); setPlaying(false); }
  }

  return (
    <div className="page-box">
      <div className="card center">
        <h2>{entry.subject} · {entry.point}</h2>
        <p className="muted">
          {idx + 1} / {items.length} · 剩余可听 {queue.remaining} · 听学只记暴露，不记掌握
          {queue.generating ? " · 正在续批生成…" : ""}
        </p>
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
