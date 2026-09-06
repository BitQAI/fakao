"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { delJson, getJson, postJson } from "@/lib/api";
import {
  readSavedQueue, writeSavedQueue, readMarked, writeMarked,
  readListenCustom, writeListenCustom, clearListenCustom,
  writeListenCustomQueue, readListenCustomQueue, clearListenCustomQueue,
} from "@/lib/progressStore";
import type { Entry, ListenPayload, MarkItem } from "@/lib/types";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";
import { ListenMarksPanel } from "./ListenMarksPanel";
import { loadListenInitial, LISTEN_PAGE, LISTEN_THRESHOLD } from "@/lib/listenInit";

const QUEUE_STORE_KEY = "fakao.listen.queue.v1";

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
  const [marksOpen, setMarksOpen] = useState(false);
  const [marked, setMarked] = useState<MarkItem[]>([]);
  const [customRange, setCustomRange] = useState<CustomRange | null>(null);
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set());
  const [remaining, setRemaining] = useState(0);
  const [playNonce, setPlayNonce] = useState(0);
  const [listenedToday, setListenedToday] = useState<Set<string>>(new Set());
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [statute, setStatute] = useState<string | null>(null);
  const [showText, setShowText] = useState(false);
  const [prefetching, setPrefetching] = useState(false);
  const prefetchRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const durRef = useRef(0);
  const exposedRef = useRef(false);

  useEffect(() => {
    const entryParam = searchParams.get("entry");
    // 优先用本地缓存的自定义队列（保持顺序不重排）
    const cachedQueue = !entryParam ? readListenCustomQueue() as ListenPayload | null : null;
    const customMeta = !entryParam ? readListenCustom() : null;
    if (cachedQueue && customMeta && cachedQueue.items?.length) {
      const savedIdx = Math.min(customMeta.idx, Math.max(cachedQueue.items.length - 1, 0));
      setQueue(cachedQueue);
      setCustomRange(customMeta.range);
      setSeenIds(new Set(customMeta.seenIds || []));
      setRemaining(customMeta.remaining ?? 0);
      setHeardTotal((cachedQueue as any).heard_total ?? 0);
      setListenedToday(new Set(cachedQueue.items.filter((i: any) => i.listened_today).map((i: any) => i.id)));
      setIdx(savedIdx);
      // 后台刷新听过数与 listen_count（保持原顺序，只更新计数）
      getJson<{ items: { entry_id: string; ts: string }[] }>("/api/reviews/history?mode=listen&limit=500")
        .then((d) => {
          const today = new Date().toISOString().slice(0, 10);
          const todayIds = Array.from(new Set(d.items.filter((it) => it.ts.startsWith(today)).map((it) => it.entry_id)));
          setListenedToday((prev) => new Set([...todayIds, ...Array.from(prev)]));
        }).catch(() => {});
      getJson<ListenPayload>(`/api/listen?limit=${LISTEN_PAGE}`).then((q) => setHeardTotal((h) => q.heard_total ?? h)).catch(() => {});
      postJson<ListenPayload>("/api/listen/custom", {
        subjects: customMeta.range.subjects,
        points: customMeta.range.points,
        limit: customMeta.limit || LISTEN_PAGE,
        exclude: customMeta.exclude || [],
      }).then((fresh) => {
        const freshMap = new Map(fresh.items.map((it) => [it.id, it as any]));
        setQueue((q) => q ? { ...q, items: q.items.map((it) => {
          const f = freshMap.get(it.id) as any;
          return f ? { ...it, listen_count: f.listen_count, listened_today: f.listened_today } : it;
        }) } : q);
        if (fresh.heard_total !== undefined) setHeardTotal(fresh.heard_total);
      }).catch(() => {});
      return;
    }
    loadListenInitial(entryParam).then((res) => {
      setQueue(res.queue);
      setIdx(res.idx);
      setCustomRange(res.customRange);
      setSeenIds(new Set(res.seenIds));
      setRemaining(res.remaining);
      setHeardTotal(res.heardTotal);
      setListenedToday(new Set(res.listenedToday));
      setDeep(res.deep);
      if (res.customRange) writeListenCustomQueue(res.queue);
    }).catch((e) => setError(String(e)));
  }, [searchParams]);

  useEffect(() => {
    getJson<{ items: MarkItem[] }>("/api/marks").then(async (d) => {
      setMarked(d.items);
      const legacy = readMarked();
      const existing = new Set(d.items.map((m) => m.entry_id));
      const pending = legacy.filter((m) => !existing.has(m.id));
      if (pending.length) {
        for (const m of pending) try { await postJson("/api/marks", { entry_id: m.id }); } catch {}
        writeMarked([]);
        const fresh = await getJson<{ items: MarkItem[] }>("/api/marks");
        setMarked(fresh.items);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!queue || queue.items.length === 0) return;
    writeSavedQueue(QUEUE_STORE_KEY, queue.items.map((i) => i.id), idx);
    if (queue.custom && customRange) {
      const c = readListenCustom();
      if (c) writeListenCustom({ ...c, idx });
      writeListenCustomQueue(queue);
    }
  }, [queue, idx, customRange]);

  useEffect(() => { durRef.current = 0; exposedRef.current = false; setShowText(false); }, [idx]);

  // 预加载：剩 LISTEN_THRESHOLD 条时后台静默续取 LISTEN_PAGE 条（只追加不跳段）
  useEffect(() => {
    if (!queue || queue.items.length === 0 || idx >= queue.items.length) return;
    const left = queue.items.length - 1 - idx;
    if (left > LISTEN_THRESHOLD) return;
    const hasMore = queue.custom ? remaining > 0 : queue.remaining > 0;
    if (!hasMore || prefetchRef.current || loadingMore) return;
    prefetchRef.current = true;
    setPrefetching(true);
    const curIds = queue.items.map((i) => i.id);
    const job = queue.custom && customRange
      ? postJson<ListenPayload>("/api/listen/custom", {
          subjects: customRange.subjects, points: customRange.points,
          limit: LISTEN_PAGE, exclude: Array.from(new Set(Array.from(seenIds).concat(curIds))),
        }).then((r) => {
          if (!r.items.length) { setRemaining(0); return; }
          const fresh = r.items.filter((it) => !curIds.includes(it.id));
          if (!fresh.length) { setRemaining(0); return; }
          setQueue((q) => (q ? { ...q, items: [...q.items, ...fresh], remaining: r.remaining } : q));
          setSeenIds((prev) => new Set(Array.from(prev).concat(fresh.map((i) => i.id))));
          setRemaining(Math.max(0, (r.remaining ?? 0) - fresh.length));
          if (r.heard_total !== undefined) setHeardTotal(r.heard_total);
          setListenedToday((prev) => {
            const next = new Set(prev);
            fresh.forEach((it) => { if ((it as any).listened_today) next.add(it.id); });
            return next;
          });
        })
      : postJson<ListenPayload>("/api/listen/more", { count: LISTEN_PAGE, exclude: curIds }).then((r) => {
          if (!r.items.length) {
            // 全部未听已在队列中，无更新可取时停，避免剩 3 条阈值反复触发
            setQueue((q) => (q ? { ...q, remaining: 0 } : q));
            return;
          }
          setQueue((q) => (q ? { ...q, items: [...q.items, ...r.items], remaining: r.remaining } : q));
          setListenedToday((prev) => {
            const next = new Set(prev);
            r.items.forEach((it) => { if ((it as any).listened_today) next.add(it.id); });
            return next;
          });
        });
    void job.catch(() => {}).finally(() => { prefetchRef.current = false; setPrefetching(false); });
  }, [queue, idx, loadingMore, customRange, seenIds, remaining]);

  // 音频预热：提前加载下一条，避免切换时等待合成
  useEffect(() => {
    if (!queue || idx >= queue.items.length) return;
    const nextItem = queue.items[idx + 1];
    if (!nextItem) return;
    const a = new Audio(`/api/audio/${nextItem.id}`);
    a.preload = "auto";
    return () => { a.pause(); a.removeAttribute("src"); };
  }, [queue, idx]);

  async function removeMark(m: MarkItem) { try { await delJson(`/api/marks/${m.id}`); setMarked((p) => p.filter((x) => x.id !== m.id)); } catch (e) { setNotice("取消失败：" + String(e)); } }
  async function clearMarks() { try { await delJson("/api/marks"); setMarked([]); } catch (e) { setNotice("清空失败：" + String(e)); } }
  async function replayMarked(m: MarkItem) {
    setNotice(""); if (!queue) return;
    const inIdx = queue.items.findIndex((i) => i.id === m.entry_id);
    if (inIdx >= 0) setIdx(inIdx);
    else { try { const e = await getJson<Entry>(`/api/entries/${encodeURIComponent(m.entry_id)}`); setQueue((q) => q ? { ...q, items: [e, ...q.items.filter((i) => i.id !== e.id)] } : q); setIdx(0); } catch { setNotice("重背失败：条目不存在或已下架。"); return; } }
    setPlayNonce((n) => n + 1); setMarksOpen(false);
  }
  function viewMarked(m: MarkItem) { window.location.href = `/study?view=read&entry=${encodeURIComponent(m.entry_id)}`; }

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
            <button className="btn btn-primary" onClick={() => setPickerOpen(true)}>自定义范围学习</button>
            <button className="btn" onClick={() => setMarksOpen(true)}>已标记（{marked.length}）</button>
          </div>
        </div>
        {marksOpen && <div className="source-modal" onClick={() => setMarksOpen(false)}><div className="source-panel" onClick={(e) => e.stopPropagation()}><ListenMarksPanel marked={marked} onClose={() => setMarksOpen(false)} onRemove={(m) => void removeMark(m)} onReplay={(m) => void replayMarked(m)} onView={viewMarked} onClear={() => void clearMarks()} /></div></div>}
        <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onConfirm={(r) => void applyCustom(r)} />
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
            <div>
              <div className="row"><button className="btn btn-primary" onClick={() => { clearListenCustom(); clearListenCustomQueue(); setPickerOpen(true); }}>重新选择范围</button></div>
              {customRange && remaining > 0 ? (
                <div className="continue-box">
                  <p className="muted">剩余未听 {remaining} 段，选择下一组或部分：</p>
                  <div className="row">
                    <button className="btn" disabled={loadingMore} onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: 20 })}>下一组 20</button>
                    <button className="btn" disabled={loadingMore} onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: 50 })}>下一组 50</button>
                  </div>
                  <div className="continue-custom">
                    <input type="number" min={1} max={50} placeholder="自定义数量" value={moreCount} onChange={(e) => setMoreCount(e.target.value)} />
                    <button className="btn btn-primary" disabled={loadingMore || !moreCount} onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: Number(moreCount) })}>继续</button>
                  </div>
                  {notice && <p className="muted">{notice}</p>}
                </div>
              ) : <p className="muted">所选范围已全部听完，可重新选择范围。</p>}
            </div>
          ) : (
            <div className="continue-box">
              <p className="muted">继续听？选择数量：</p>
              <div className="row">
                <button className="btn" disabled={loadingMore} onClick={() => void loadMore(5)}>再听 5 段</button>
                <button className="btn" disabled={loadingMore} onClick={() => void loadMore(10)}>再听 10 段</button>
              </div>
              <div className="continue-custom">
                <input type="number" min={1} max={50} placeholder="自定义数量" value={moreCount} onChange={(e) => setMoreCount(e.target.value)} />
                <button className="btn btn-primary" disabled={loadingMore || !moreCount} onClick={() => void loadMore(Number(moreCount))}>继续</button>
              </div>
              {notice && <p className="muted">{notice}</p>}
            </div>
          )}
        </div>
        <SourceViewer source={source} onClose={() => setSource(null)} />
        <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onConfirm={(r) => void applyCustom(r)} />
      </div>
    );
  }

  async function applyCustom(range: CustomRange, opts?: { exclude?: string[]; limit?: number }) {
    setLoadingMore(true); setNotice("");
    try {
      const exclude = opts?.exclude ?? [];
      const limit = opts?.limit ?? LISTEN_PAGE;
      const r = await postJson<ListenPayload>("/api/listen/custom", { subjects: range.subjects, points: range.points, limit, exclude });
      if (!r.items.length) {
        if (exclude.length) setRemaining(0);
        setNotice(exclude.length ? "剩余已全部听完。" : "所选范围暂无听学内容（可能尚未合成音频）。");
        setPickerOpen(false); return;
      }
      setQueue(r); setHeardTotal(r.heard_total ?? heardTotal);
      const newSeen = new Set([...exclude, ...r.items.map((i) => i.id)]);
      setSeenIds(newSeen);
      const newRemaining = Math.max(0, (r.remaining ?? 0) - r.items.length);
      setRemaining(newRemaining);
      writeListenCustom({ range, seenIds: Array.from(newSeen), remaining: newRemaining, idx: 0, limit, exclude, ts: Date.now() });
      writeListenCustomQueue(r);
      getJson<{ items: { entry_id: string; ts: string }[] }>("/api/reviews/history?mode=listen&limit=500")
        .then((d) => {
          const today = new Date().toISOString().slice(0, 10);
          const todayIds = Array.from(new Set(d.items.filter((it) => it.ts.startsWith(today)).map((it) => it.entry_id)));
          const newIds = r.items.filter((i) => i.listened_today).map((i) => i.id);
          setListenedToday(new Set([...todayIds, ...newIds]));
        }).catch(() => setListenedToday(new Set(r.items.filter((i) => i.listened_today).map((i) => i.id))));
      setCustomRange(range); setDeep(false); setIdx(0); setPlaying(false); setPickerOpen(false);
    } catch (e) { setNotice("加载失败：" + String(e)); } finally { setLoadingMore(false); }
  }

  async function loadMore(count: number) {
    if (count < 1 || count > 50) return;
    setLoadingMore(true); setNotice("");
    try {
      const r = await postJson<ListenPayload>("/api/listen/more", { count, exclude: items.map((i) => i.id) });
      if (!r.items.length) { setNotice("没有更多听学内容了。"); return; }
      setQueue((q) => (q ? { ...q, items: [...q.items, ...r.items], remaining: r.remaining } : q));
      setListenedToday((prev) => { const next = new Set(prev); r.items.forEach((it) => { if ((it as any).listened_today) next.add(it.id); }); return next; });
      setIdx(items.length); setPlaying(false);
    } catch (e) { setNotice("加载失败：" + String(e)); } finally { setLoadingMore(false); setMoreCount(""); }
  }

  function markExposed() {
    if (exposedRef.current || durRef.current < 10) return;
    exposedRef.current = true;
    if (!entry.listen_count) setHeardTotal((n) => n + 1);
    setListenedToday((prev) => new Set(prev).add(entry.id));
    setQueue((q) => q ? { ...q, items: q.items.map((it) => it.id === entry.id ? { ...it, listen_count: (it.listen_count || 0) + 1, listened_today: true } as any : it) } : q);
    void postJson("/api/reviews", { entry_id: entry.id, mode: "listen", result: "exposed", duration_sec: Math.round(durRef.current || 0) });
  }
  function next() { markExposed(); if (idx + 1 < items.length) setIdx(idx + 1); else { setIdx(items.length); setPlaying(false); } }
  function prev() { markExposed(); if (idx > 0) setIdx(idx - 1); }
  const isMarked = marked.some((m) => m.entry_id === entry.id);
  async function toggleMark() {
    if (isMarked) {
      const m = marked.find((x) => x.entry_id === entry.id); if (!m) return;
      try { await delJson(`/api/marks/${m.id}`); setMarked((p) => p.filter((x) => x.id !== m.id)); } catch (e) { setNotice("取消失败：" + String(e)); }
    } else {
      try { await postJson("/api/marks", { entry_id: entry.id }); const fresh = await getJson<{ items: MarkItem[] }>("/api/marks"); setMarked(fresh.items); } catch (e) { setNotice("标记失败：" + String(e)); }
    }
  }
  return (
    <div className="page-box">
      <div className="mode-row">
        <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>自定义范围</button>
        {queue.custom && <button className="btn btn-ghost mode-btn" onClick={() => { clearListenCustom(); clearListenCustomQueue(); setPickerOpen(true); }}>重新选择</button>}
        <button className="btn btn-ghost mode-btn" onClick={() => setMarksOpen(true)}>已标记（{marked.length}）</button>
      </div>
      {notice && <p className="muted">{notice}</p>}
      {deep && idx === 0 && <p className="muted">已定位到目标条目，可先听该条，其余按队列继续。</p>}
      <div className="card center">
        <h2>{entry.subject} · {entry.point}{isMarked && <span className="badge">已标记</span>}{(entry.listened_today || listenedToday.has(entry.id)) && <span className="badge">今日已听</span>}{entry.listen_count ? <span className="badge">已听 {entry.listen_count} 次</span> : <span className="badge">未听</span>}</h2>
        <p className="muted">第 {idx + 1} 段 / 队列 {items.length} · {entry.listen_count ? `本条已听 ${entry.listen_count} 次` : "本条未听"} · 今日累计 {listenedToday.size} 条 · 累计已听 {heardTotal} · 剩余可听 {queue.remaining}{queue.generating ? " · 正在续批生成…" : ""}{prefetching ? " · 后面内容加载中…" : ""}</p>
        <p className="muted" style={{ fontSize: 12 }}>听学只记暴露，不记掌握</p>
        <audio ref={audioRef} controls autoPlay key={`${entry.id}-${playNonce}`} src={`/api/audio/${entry.id}`} onLoadedMetadata={(e) => { durRef.current = Math.round(e.currentTarget.duration || 0); }} onPlay={() => setPlaying(true)} onPause={() => { setPlaying(false); markExposed(); }} onEnded={() => { markExposed(); next(); }} onError={() => setError("音频生成中或不可用，请稍后重试")} />
        <div className="row">
          <button className="btn btn-ghost" disabled={idx === 0} onClick={prev}>上一个</button>
          <button className="btn btn-ghost" onClick={toggleMark}>{isMarked ? "已标记 ✓" : "标记"}</button>
          <button className="btn btn-ghost" onClick={next}>{playing ? "跳过" : "下一段"}</button>
        </div>
        <div className="row">
          <button className="btn btn-ghost" onClick={() => setShowText((s) => !s)}>
            {showText ? "收起原文" : "显示原文"}
          </button>
        </div>
        {showText && (
          <div className="analysis" style={{ textAlign: "left" }}>
            <p><b>场景：</b>{entry.anchor}</p>
            <p><b>结论：</b>{entry.conclusion}</p>
            {entry.note && <p className="note">⚠ {entry.note}</p>}
            {entry.tts_text && <p className="muted">播报文本：{entry.tts_text}</p>}
            {entry.statutes.length > 0 && (
              <div className="source-chips" style={{ marginTop: 8 }}>
                {entry.statutes.map((st, i) => (
                  <button key={i} className="chip" onClick={() => setStatute(st)}>{st}</button>
                ))}
              </div>
            )}
          </div>
        )}
        {entry.cases.length > 0 && <div className="source-chips" style={{ justifyContent: "center" }}>{entry.cases.map((c, i) => (<button key={i} className="chip" onClick={() => setSource({ kind: "case", ref: c.source, loc: c.loc })}>查看原文 · 案例 {i + 1}</button>))}</div>}
      </div>
      <SourceViewer source={source} statute={statute} onClose={() => { setSource(null); setStatute(null); }} />
      {marksOpen && <div className="source-modal" onClick={() => setMarksOpen(false)}><div className="source-panel" onClick={(e) => e.stopPropagation()}><ListenMarksPanel marked={marked} onClose={() => setMarksOpen(false)} onRemove={removeMark} onReplay={replayMarked} onView={viewMarked} onClear={clearMarks} /></div></div>}
      <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onConfirm={(r) => void applyCustom(r)} />
    </div>
  );
}
