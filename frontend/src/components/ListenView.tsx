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
import { useAiShortcut } from "@/lib/aiShortcut";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";
import { ListenMarksPanel } from "./ListenMarksPanel";
import ListenSegment from "./listen/ListenSegment";
import ListenFinishCard from "./listen/ListenFinishCard";
import { useListenCustom } from "./listen/useListenCustom";
import { useListenMarked } from "./listen/useListenMarked";
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
  const [playNonce, setPlayNonce] = useState(0);
  const [listenedToday, setListenedToday] = useState<Set<string>>(new Set());
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [statute, setStatute] = useState<string | null>(null);
  const [showText, setShowText] = useState(true);
  const [prefetching, setPrefetching] = useState(false);
  const prefetchRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const durRef = useRef(0);
  const playedRef = useRef(0);
  const exposedRef = useRef(false);
  // 断线重连：重试计数 / 定时器 / 断点续播位置 / 是否处于恢复中
  const retryRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);
  const stallTimerRef = useRef<number | null>(null);
  const resumeRef = useRef(0);
  const recoveringRef = useRef(false);
  const MAX_RETRY = 3;

  // 问 AI 快捷入口 + 历史条数徽标（与看背共用）
  const { askAi, aiLabel } = useAiShortcut(queue?.items[idx] ?? null);

  const custom = useListenCustom({
    queue, setQueue, heardTotal, setHeardTotal, setIdx, setPlaying,
    setDeep, setNotice, setListenedToday,
  });
  const {
    customRange, setCustomRange, seenIds, setSeenIds, remaining, setRemaining,
    loadingMore, moreCount, setMoreCount, pickerOpen, setPickerOpen,
    applyCustom, loadMore, resetRange,
  } = custom;

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
        kinds: customMeta.range.kinds ?? [],
        laws: customMeta.range.laws ?? [],
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
    // setCustomRange/setSeenIds/setRemaining 来自 useListenCustom，均为 useState setter（稳定）
  }, [searchParams, setCustomRange, setSeenIds, setRemaining]);

  const marks = useListenMarked({ onError: setNotice });

  useEffect(() => {
    if (!queue || queue.items.length === 0) return;
    writeSavedQueue(QUEUE_STORE_KEY, queue.items.map((i) => i.id), idx);
    if (queue.custom && customRange) {
      const c = readListenCustom();
      if (c) writeListenCustom({ ...c, idx });
      writeListenCustomQueue(queue);
    }
  }, [queue, idx, customRange]);

  useEffect(() => {
    durRef.current = 0; playedRef.current = 0; exposedRef.current = false;
    retryRef.current = 0; resumeRef.current = 0; recoveringRef.current = false;
    if (retryTimerRef.current !== null) { window.clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
    if (stallTimerRef.current !== null) { window.clearTimeout(stallTimerRef.current); stallTimerRef.current = null; }
    setNotice("");
    setShowText(true);
  }, [idx]);

  // 卸载时清理重连定时器
  useEffect(() => () => {
    if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current);
    if (stallTimerRef.current !== null) window.clearTimeout(stallTimerRef.current);
  }, []);

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
          kinds: customRange.kinds ?? [], laws: customRange.laws ?? [],
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
  }, [queue, idx, loadingMore, customRange, seenIds, remaining, setRemaining, setSeenIds, setHeardTotal, setQueue]);

  // 音频预热：提前加载下一条，避免切换时等待合成
  useEffect(() => {
    if (!queue || idx >= queue.items.length) return;
    const nextItem = queue.items[idx + 1];
    if (!nextItem) return;
    const a = new Audio(`/api/audio/${nextItem.id}`);
    a.preload = "auto";
    return () => { a.pause(); a.removeAttribute("src"); };
  }, [queue, idx]);

  async function replayMarked(m: MarkItem) {
    setNotice(""); if (!queue) return;
    const inIdx = queue.items.findIndex((i) => i.id === m.entry_id);
    if (inIdx >= 0) setIdx(inIdx);
    else { try { const e = await getJson<Entry>(`/api/entries/${encodeURIComponent(m.entry_id)}`); setQueue((q) => q ? { ...q, items: [e, ...q.items.filter((i) => i.id !== e.id)] } : q); setIdx(0); } catch { setNotice("重背失败：条目不存在或已下架。"); return; } }
    setPlayNonce((n) => n + 1); marks.setMarksOpen(false);
  }
  function viewMarked(m: MarkItem) { window.location.href = `/study?view=read&entry=${encodeURIComponent(m.entry_id)}`; }

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!queue) return <p className="muted">加载中…</p>;
  const items = queue.items;
  if (items.length === 0) {
    return (
      <div className="page-box">
        <ListenFinishCard
          empty custom={false} itemsCount={0} remaining={0} hasRange={false}
          queueRemaining={queue.generating ? 1 : queue.remaining}
          loadingMore={loadingMore} moreCount={moreCount} notice={notice}
          onCountChange={setMoreCount} onPickRange={() => setPickerOpen(true)}
          onClearRange={() => {}} onContinueRange={() => {}} onLoadMore={() => {}}>
          <div className="row">
            <button className="btn btn-primary" onClick={() => setPickerOpen(true)}>自定义范围学习</button>
            <button className="btn" onClick={() => marks.setMarksOpen(true)}>已标记（{marks.marked.length}）</button>
          </div>
        </ListenFinishCard>
        {marks.marksOpen && <div className="source-modal" onClick={() => marks.setMarksOpen(false)}><div className="source-panel" onClick={(e) => e.stopPropagation()}><ListenMarksPanel marked={marks.marked} onClose={() => marks.setMarksOpen(false)} onRemove={(m) => void marks.removeMark(m)} onReplay={(m) => void replayMarked(m)} onView={viewMarked} onClear={() => void marks.clearMarks()} /></div></div>}
        <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onConfirm={(r) => void applyCustom(r)} />
      </div>
    );
  }

  const entry: Entry = items[idx];
  if (idx >= items.length) {
    return (
      <div className="page-box">
        <ListenFinishCard
          empty={false} custom={Boolean(queue.custom)} itemsCount={items.length}
          remaining={remaining} queueRemaining={queue.remaining} hasRange={Boolean(customRange)}
          loadingMore={loadingMore} moreCount={moreCount} notice={notice}
          onCountChange={setMoreCount} onPickRange={() => setPickerOpen(true)}
          onClearRange={resetRange}
          onContinueRange={(limit) => {
            if (customRange) void applyCustom(customRange, { exclude: Array.from(seenIds), limit });
          }}
          onLoadMore={(count) => void loadMore(count)} />
        <SourceViewer source={source} onClose={() => setSource(null)} />
        <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onConfirm={(r) => void applyCustom(r)} />
      </div>
    );
  }

  function clearStallTimer() {
    if (stallTimerRef.current !== null) {
      window.clearTimeout(stallTimerRef.current);
      stallTimerRef.current = null;
    }
  }

  function handleAudioError() {
    clearStallTimer();
    const n = retryRef.current;
    // 404/503/断网在浏览器侧都表现为媒体错误，无法可靠区分：统一按瞬时故障退避重试
    if (n < MAX_RETRY) {
      retryRef.current = n + 1;
      resumeRef.current = playedRef.current;
      recoveringRef.current = true;
      setNotice(`网络波动，正在重连（${n + 1}/${MAX_RETRY}）…`);
      if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current);
      const delay = [1500, 3000, 6000][n] ?? 6000;
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null;
        setPlayNonce((v) => v + 1); // remount 音频元素重建请求，加载后自动断点续播
      }, delay);
    } else {
      recoveringRef.current = false;
      setNotice("音频加载失败，已停止重连。请检查网络，或点「下一个」跳过。");
    }
  }

  // 长时间缓冲无进展视为卡死，走同样的重连路径（10 秒看门狗）
  function armStallTimer() {
    clearStallTimer();
    stallTimerRef.current = window.setTimeout(() => {
      stallTimerRef.current = null;
      handleAudioError();
    }, 10000);
  }

  function handleAudioRecovered() {
    clearStallTimer();
    retryRef.current = 0;
    if (recoveringRef.current) {
      recoveringRef.current = false;
      setNotice("");
    }
  }

  function markExposed(force = false) {
    if (exposedRef.current) return;
    // 短音频（<10s，库内 337 条 / 14.6%）按旧阈值 dur>=10 永不计数。
    // 新规则：播完即记；中途切歌/暂停则按实际播放位置 >= min(8, duration*0.8) 才记。
    if (!force) {
      const dur = durRef.current || 0;
      const played = playedRef.current || 0;
      const threshold = dur > 0 ? Math.min(8, dur * 0.8) : 8;
      if (played < threshold) return;
    }
    exposedRef.current = true;
    if (!entry.listen_count) setHeardTotal((n) => n + 1);
    setListenedToday((prev) => new Set(prev).add(entry.id));
    setQueue((q) => q ? { ...q, items: q.items.map((it) => it.id === entry.id ? { ...it, listen_count: (it.listen_count || 0) + 1, listened_today: true } as any : it) } : q);
    void postJson("/api/reviews", { entry_id: entry.id, mode: "listen", result: "exposed", duration_sec: Math.round(playedRef.current || durRef.current || 0) });
  }
  function next() { markExposed(); if (idx + 1 < items.length) setIdx(idx + 1); else { setIdx(items.length); setPlaying(false); } }
  function prev() { markExposed(); if (idx > 0) setIdx(idx - 1); }
  const isMarked = marks.isMarked(entry.id);
  return (
    <div className="page-box">
      <div className="mode-row">
        <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>自定义范围</button>
        {queue.custom && <button className="btn btn-ghost mode-btn" onClick={() => { resetRange(); setPickerOpen(true); }}>重新选择</button>}
        <button className="btn btn-ghost mode-btn" onClick={() => marks.setMarksOpen(true)}>已标记（{marks.marked.length}）</button>
      </div>
      {notice && <p className="muted">{notice}</p>}
      {deep && idx === 0 && <p className="muted">已定位到目标条目，可先听该条，其余按队列继续。</p>}
      <ListenSegment
        entry={entry} idx={idx} total={items.length}
        heardTotal={heardTotal} remaining={queue.remaining}
        generating={Boolean(queue.generating)} prefetching={prefetching}
        playing={playing} todayCount={listenedToday.size}
        listenedToday={listenedToday.has(entry.id)}
        isMarked={isMarked} showText={showText} aiLabel={aiLabel}
        audio={{
          ref: audioRef,
          src: `/api/audio/${entry.id}`,
          audioKey: `${entry.id}-${playNonce}`,
          onLoadedMetadata: (e) => {
            durRef.current = Math.round(e.currentTarget.duration || 0);
            if (resumeRef.current > 0) {
              const dur = e.currentTarget.duration || 0;
              try {
                e.currentTarget.currentTime = dur > 0
                  ? Math.max(0, Math.min(resumeRef.current, dur - 0.25))
                  : resumeRef.current;
              } catch { /* 忽略 seek 失败 */ }
              resumeRef.current = 0;
            }
          },
          onTimeUpdate: (e) => {
            playedRef.current = Math.max(playedRef.current, e.currentTarget.currentTime || 0);
          },
          onPlay: () => { setPlaying(true); handleAudioRecovered(); },
          onCanPlay: handleAudioRecovered,
          onWaiting: armStallTimer,
          onStalled: armStallTimer,
          onPause: (e) => {
            setPlaying(false);
            playedRef.current = Math.max(playedRef.current, e.currentTarget.currentTime || 0);
            markExposed();
          },
          onEnded: (e) => {
            playedRef.current = Math.max(
              playedRef.current, e.currentTarget.currentTime || e.currentTarget.duration || 0);
            markExposed(true);
            next();
          },
          onError: handleAudioError,
        }}
        onToggleText={() => setShowText((s) => !s)}
        onPrev={prev} onNext={next} onToggleMark={() => void marks.toggleMark(entry.id)}
        onAskAi={askAi}
        onStatute={(st) => setStatute(st)}
        onCase={(c) => setSource({ kind: "case", ref: c.source, loc: c.loc })}
      />
      <SourceViewer source={source} statute={statute} onClose={() => { setSource(null); setStatute(null); }} />
      {marks.marksOpen && <div className="source-modal" onClick={() => marks.setMarksOpen(false)}><div className="source-panel" onClick={(e) => e.stopPropagation()}><ListenMarksPanel marked={marks.marked} onClose={() => marks.setMarksOpen(false)} onRemove={marks.removeMark} onReplay={replayMarked} onView={viewMarked} onClear={() => void marks.clearMarks()} /></div></div>}
      <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)} onConfirm={(r) => void applyCustom(r)} />
    </div>
  );
}
