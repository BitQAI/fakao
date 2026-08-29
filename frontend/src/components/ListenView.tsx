"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson, postJson } from "@/lib/api";
import type { Entry, ListenPayload } from "@/lib/types";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";

const QUEUE_STORE_KEY = "fakao.listen.queue.v1";

function readSaved(): { ids: string[]; idx: number } | null {
  try {
    const raw = localStorage.getItem(QUEUE_STORE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (Array.isArray(data.ids) && typeof data.idx === "number") return data;
  } catch { /* 忽略损坏的本地缓存 */ }
  return null;
}

function writeSaved(ids: string[], idx: number) {
  try {
    localStorage.setItem(QUEUE_STORE_KEY, JSON.stringify({ ids, idx }));
  } catch { /* 忽略存储失败 */ }
}

export default function ListenView() {
  const searchParams = useSearchParams();
  const [queue, setQueue] = useState<ListenPayload | null>(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deep, setDeep] = useState(false);
  const [heardTotal, setHeardTotal] = useState(0);
  const [moreCount, setMoreCount] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [source, setSource] = useState<SourceTarget | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const durRef = useRef(0);
  const exposedRef = useRef(false);

  useEffect(() => {
    const entryParam = searchParams.get("entry");
    const targetReq = entryParam
      ? getJson<Entry>(`/api/entries/${encodeURIComponent(entryParam)}`)
          .catch(() => null)
      : Promise.resolve(null);
    Promise.all([getJson<ListenPayload>("/api/listen"), targetReq])
      .then(([q, target]) => {
        let items = q.items;
        if (target) {
          items = [target, ...q.items.filter((i) => i.id !== target.id)];
          setDeep(true);
        }
        const saved = readSaved();
        let startIdx = 0;
        if (!entryParam && saved && saved.ids.length === items.length &&
            saved.ids.every((id, i) => id === items[i].id)) {
          startIdx = Math.min(saved.idx, Math.max(items.length - 1, 0));
        }
        setHeardTotal(q.heard_total ?? 0);
        setQueue({ ...q, items });
        setIdx(startIdx);
      })
      .catch((e) => setError(String(e)));
  }, [searchParams]);

  // 队列位置持久化：刷新/离开后回来可恢复
  useEffect(() => {
    if (!queue || queue.items.length === 0) return;
    writeSaved(queue.items.map((i) => i.id), idx);
  }, [queue, idx]);

  // 切条目时重置播放统计与去重标记
  useEffect(() => {
    durRef.current = 0;
    exposedRef.current = false;
  }, [idx]);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!queue) return <p className="muted">加载中…</p>;

  const items = queue.items;
  if (items.length === 0) {
    return (
      <div className="page-box">
        <div className="card">
          <p>{queue.generating ? "正在生成更多听学内容…" : "暂无听学内容。"}</p>
          {queue.remaining === 0 && <p className="muted">剩余不足时系统会自动续批生成。</p>}
          <div className="row">
            <button className="btn btn-primary" onClick={() => setPickerOpen(true)}>
              自定义范围学习
            </button>
          </div>
        </div>
        <CustomRangePicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          onConfirm={(range) => void applyCustom(range)}
        />
      </div>
    );
  }

  const entry: Entry = items[idx];

  if (idx >= items.length) {
    return (
      <div className="page-box">
        <div className="card center">
          <h2>{queue.custom ? "自定义范围已学完" : "本轮听学完成"}</h2>
          <p className="muted">共听了 {items.length} 段 · 剩余可听 {queue.remaining}</p>
          {queue.custom ? (
            <div className="row">
              <button className="btn btn-primary" onClick={() => setPickerOpen(true)}>
                重新选择范围
              </button>
            </div>
          ) : (
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
          )}
        </div>
        <SourceViewer source={source} onClose={() => setSource(null)} />
        <CustomRangePicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          onConfirm={(range) => void applyCustom(range)}
        />
      </div>
    );
  }

  async function applyCustom(range: CustomRange) {
    setLoadingMore(true);
    setNotice("");
    try {
      const r = await postJson<ListenPayload>("/api/listen/custom", {
        subjects: range.subjects, points: range.points,
      });
      if (!r.items.length) {
        setNotice("所选范围暂无听学内容（可能尚未合成音频）。");
        setPickerOpen(false);
        return;
      }
      setQueue(r);
      setHeardTotal(r.heard_total ?? heardTotal);
      setDeep(false);
      setIdx(0);
      setPlaying(false);
      setPickerOpen(false);
    } catch (e) {
      setNotice("加载失败：" + String(e));
    } finally {
      setLoadingMore(false);
    }
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

  function markExposed() {
    if (exposedRef.current) return;
    exposedRef.current = true;
    if (!entry.listen_count) setHeardTotal((n) => n + 1);
    void postJson("/api/reviews", {
      entry_id: entry.id, mode: "listen", result: "exposed",
      duration_sec: Math.round(durRef.current || 0),
    });
  }

  function next() {
    if (idx + 1 < items.length) setIdx(idx + 1);
    else { setIdx(items.length); setPlaying(false); }
  }

  return (
    <div className="page-box">
      <div className="mode-row">
        <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>
          自定义范围
        </button>
        {queue.custom && (
          <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>
            重新选择
          </button>
        )}
      </div>
      {notice && <p className="muted">{notice}</p>}
      {deep && idx === 0 && <p className="muted">已定位到目标条目，可先听该条，其余按队列继续。</p>}
      <div className="card center">
        <h2>
          {entry.subject} · {entry.point}
          {entry.listen_count ? <span className="badge">已听 {entry.listen_count} 次</span> : ""}
        </h2>
        <p className="muted">第 {idx + 1} 段 / 队列 {items.length}</p>
        <p className="muted">
          累计已听 {heardTotal} · 剩余可听 {queue.remaining} · 听学只记暴露，不记掌握
          {queue.generating ? " · 正在续批生成…" : ""}
        </p>
        <audio
          ref={audioRef}
          controls
          autoPlay
          src={`/api/audio/${entry.id}`}
          onLoadedMetadata={(e) => { durRef.current = Math.round(e.currentTarget.duration || 0); }}
          onPlay={() => setPlaying(true)}
          onPause={() => {
            setPlaying(false);
            if (durRef.current >= 15) markExposed();  // 听了 15 秒以上也算暴露
          }}
          onEnded={() => {
            markExposed();
            next();
          }}
          onError={() => setError("音频生成中或不可用，请稍后重试")}
        />
        <div className="row">
          <button className="btn btn-ghost" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>上一个</button>
          <button className="btn btn-ghost" onClick={() => { markExposed(); next(); }}>
            {playing ? "跳过" : "下一段"}
          </button>
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
      <CustomRangePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onConfirm={(range) => void applyCustom(range)}
      />
    </div>
  );
}
