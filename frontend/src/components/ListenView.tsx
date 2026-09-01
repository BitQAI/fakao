"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { delJson, getJson, postJson } from "@/lib/api";
import {
  readSavedQueue, writeSavedQueue,
  readMarked, writeMarked,
} from "@/lib/progressStore";
import type { Entry, ListenPayload, MarkItem } from "@/lib/types";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";

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
        const saved = readSavedQueue(QUEUE_STORE_KEY);
        let startIdx = 0;
        if (!entryParam && saved && saved.ids.length === items.length &&
            saved.ids.every((id, i) => id === items[i].id)) {
          startIdx = Math.min(saved.idx, Math.max(items.length - 1, 0));
        }
        setHeardTotal(q.heard_total ?? 0);
        setListenedToday(new Set(items.filter((i) => i.listened_today).map((i) => i.id)));
        setQueue({ ...q, items });
        setIdx(startIdx);
      })
      .catch((e) => setError(String(e)));
  }, [searchParams]);

  useEffect(() => {
    getJson<{ items: MarkItem[] }>("/api/marks")
      .then(async (d) => {
        setMarked(d.items);
        // 迁移旧 localStorage 标记（单用户设备级 → 服务端，逐条容错）
        const legacy = readMarked();
        const existing = new Set(d.items.map((m) => m.entry_id));
        const pending = legacy.filter((m) => !existing.has(m.id));
        if (pending.length) {
          for (const m of pending) {
            try { await postJson("/api/marks", { entry_id: m.id }); } catch { /* 保留本地 */ }
          }
          writeMarked([]);
          const fresh = await getJson<{ items: MarkItem[] }>("/api/marks");
          setMarked(fresh.items);
        }
      })
      .catch(() => { /* 服务端不可用时保持空标记 */ });
  }, []);

  // 队列位置持久化：刷新/离开后回来可恢复
  useEffect(() => {
    if (!queue || queue.items.length === 0) return;
    writeSavedQueue(QUEUE_STORE_KEY, queue.items.map((i) => i.id), idx);
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
            <button className="btn" onClick={() => setMarksOpen(true)}>
              已标记（{marked.length}）
            </button>
          </div>
        </div>
        {marksOpen && (
          <div className="source-modal" onClick={() => setMarksOpen(false)}>
            <div className="source-panel" onClick={(e) => e.stopPropagation()}>
              {marksPanel()}
            </div>
          </div>
        )}
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
            <div>
              <div className="row">
                <button className="btn btn-primary" onClick={() => setPickerOpen(true)}>
                  重新选择范围
                </button>
              </div>
              {customRange && remaining > 0 ? (
                <div className="continue-box">
                  <p className="muted">剩余未听 {remaining} 段，选择下一组或部分：</p>
                  <div className="row">
                    <button className="btn" disabled={loadingMore}
                      onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: 20 })}>
                      下一组 20
                    </button>
                    <button className="btn" disabled={loadingMore}
                      onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: 50 })}>
                      下一组 50
                    </button>
                  </div>
                  <div className="continue-custom">
                    <input
                      type="number" min={1} max={50} placeholder="自定义数量"
                      value={moreCount}
                      onChange={(e) => setMoreCount(e.target.value)}
                    />
                    <button className="btn btn-primary" disabled={loadingMore || !moreCount}
                      onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: Number(moreCount) })}>
                      继续
                    </button>
                  </div>
                  {notice && <p className="muted">{notice}</p>}
                </div>
              ) : (
                <p className="muted">所选范围已全部听完，可重新选择范围。</p>
              )}
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

  async function applyCustom(range: CustomRange,
                             opts?: { exclude?: string[]; limit?: number }) {
    setLoadingMore(true);
    setNotice("");
    try {
      const r = await postJson<ListenPayload>("/api/listen/custom", {
        subjects: range.subjects, points: range.points,
        limit: opts?.limit ?? 100,
        exclude: opts?.exclude ?? [],
      });
      if (!r.items.length) {
        if (opts?.exclude?.length) setRemaining(0);
        setNotice(opts?.exclude?.length
          ? "剩余已全部听完。"
          : "所选范围暂无听学内容（可能尚未合成音频）。");
        setPickerOpen(false);
        return;
      }
      setQueue(r);
      setHeardTotal(r.heard_total ?? heardTotal);
      setSeenIds(new Set([...(opts?.exclude ?? []), ...r.items.map((i) => i.id)]));
      setRemaining(Math.max(0, (r.remaining ?? 0) - r.items.length));
      // 合并今日已听（与看背 reviewedToday 对称）
      getJson<{ items: { entry_id: string; ts: string }[] }>("/api/reviews/history?mode=listen&limit=500")
        .then((d) => {
          const today = new Date().toISOString().slice(0, 10);
          const todayIds = Array.from(new Set(d.items.filter((it) => it.ts.startsWith(today)).map((it) => it.entry_id)));
          const newIds = r.items.filter((i) => i.listened_today).map((i) => i.id);
          setListenedToday(new Set([...todayIds, ...newIds]));
        })
        .catch(() => setListenedToday(new Set(r.items.filter((i) => i.listened_today).map((i) => i.id))));
      setCustomRange(range);
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
      setListenedToday((prev) => {
        const next = new Set(prev);
        r.items.forEach((it) => { if (it.listened_today) next.add(it.id); });
        return next;
      });
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
    if (exposedRef.current || durRef.current < 10) return;
    exposedRef.current = true;
    if (!entry.listen_count) setHeardTotal((n) => n + 1);
    setListenedToday((prev) => new Set(prev).add(entry.id));
    setQueue((q) => q ? { ...q, items: q.items.map((it) => it.id === entry.id ? { ...it, listen_count: (it.listen_count || 0) + 1, listened_today: true } : it) } : q);
    void postJson("/api/reviews", {
      entry_id: entry.id, mode: "listen", result: "exposed",
      duration_sec: Math.round(durRef.current || 0),
    });
  }

  function next() {
    if (idx + 1 < items.length) setIdx(idx + 1);
    else { setIdx(items.length); setPlaying(false); }
  }

  const isMarked = marked.some((m) => m.entry_id === entry.id);

  async function toggleMark() {
    if (isMarked) {
      const m = marked.find((x) => x.entry_id === entry.id);
      if (!m) return;
      try {
        await delJson(`/api/marks/${m.id}`);
        setMarked((prev) => prev.filter((x) => x.id !== m.id));
      } catch (e) {
        setNotice("取消失败：" + String(e));
      }
    } else {
      try {
        await postJson("/api/marks", { entry_id: entry.id });
        const fresh = await getJson<{ items: MarkItem[] }>("/api/marks");
        setMarked(fresh.items);
      } catch (e) {
        setNotice("标记失败：" + String(e));
      }
    }
  }

  async function replayMarked(m: MarkItem) {
    setNotice("");
    if (!queue) return;
    const inQueueIdx = queue.items.findIndex((i) => i.id === m.entry_id);
    if (inQueueIdx >= 0) {
      setIdx(inQueueIdx);
    } else {
      try {
        const e = await getJson<Entry>(`/api/entries/${encodeURIComponent(m.entry_id)}`);
        setQueue((q) => q ? { ...q, items: [e, ...q.items.filter((i) => i.id !== e.id)] } : q);
        setIdx(0);
      } catch {
        setNotice("重背失败：条目不存在或已下架。");
        return;
      }
    }
    setPlayNonce((n) => n + 1);
    setMarksOpen(false);
  }

  function viewMarked(m: MarkItem) {
    window.location.href = `/study?view=read&entry=${encodeURIComponent(m.entry_id)}`;
  }

  async function removeMark(m: MarkItem) {
    try {
      await delJson(`/api/marks/${m.id}`);
      setMarked((prev) => prev.filter((x) => x.id !== m.id));
    } catch (e) {
      setNotice("取消失败：" + String(e));
    }
  }

  async function clearMarks() {
    try {
      await delJson("/api/marks");
      setMarked([]);
    } catch (e) {
      setNotice("清空失败：" + String(e));
    }
  }

  function marksPanel() {
    return (
      <>
        <div className="ai-chat-head">
          <b>已标记条目（{marked.length}）</b>
          <button onClick={() => setMarksOpen(false)}>×</button>
        </div>
        <div className="source-body">
          {marked.length === 0 ? (
            <p className="muted">暂无标记。听学时点「标记」收藏想重背的条目。</p>
          ) : (
            <div className="history-list">
              {marked.map((m) => (
                <div key={m.id} className="card history-card">
                  <div className="history-head">
                    <span className="tag">{m.entry.subject}</span>
                    <button className="badge-btn" onClick={() => void removeMark(m)}>
                      取消标记
                    </button>
                  </div>
                  <p className="history-stem">{m.entry.point}</p>
                  <div className="row">
                    <button className="btn" onClick={() => void replayMarked(m)}>重背</button>
                    <button className="btn btn-primary" onClick={() => viewMarked(m)}>查看</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        {marked.length > 0 && (
          <div className="pick-footer">
            <button className="btn" onClick={() => void clearMarks()}>
              清空标记
            </button>
          </div>
        )}
      </>
    );
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
        <button className="btn btn-ghost mode-btn" onClick={() => setMarksOpen(true)}>
          已标记（{marked.length}）
        </button>
      </div>
      {notice && <p className="muted">{notice}</p>}
      {deep && idx === 0 && <p className="muted">已定位到目标条目，可先听该条，其余按队列继续。</p>}
      <div className="card center">
        <h2>
          {entry.subject} · {entry.point}
          {isMarked && <span className="badge">已标记</span>}
          {(entry.listened_today || listenedToday.has(entry.id)) && <span className="badge">今日已听</span>}
          {entry.listen_count ? <span className="badge">已听 {entry.listen_count} 次</span> : <span className="badge">未听</span>}
        </h2>
        <p className="muted">
          第 {idx + 1} 段 / 队列 {items.length} · {entry.listen_count ? `本条已听 ${entry.listen_count} 次` : "本条未听"} · 今日累计 {listenedToday.size} 条 · 累计已听 {heardTotal} · 剩余可听 {queue.remaining}
          {queue.generating ? " · 正在续批生成…" : ""}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>听学只记暴露，不记掌握</p>
        <audio
          ref={audioRef}
          controls
          autoPlay
          key={`${entry.id}-${playNonce}`}
          src={`/api/audio/${entry.id}`}
          onLoadedMetadata={(e) => { durRef.current = Math.round(e.currentTarget.duration || 0); }}
          onPlay={() => setPlaying(true)}
          onPause={() => {
            setPlaying(false);
            markExposed();  // 暂停/播完且 ≥10s 才算暴露
          }}
          onEnded={() => {
            markExposed();
            next();
          }}
          onError={() => setError("音频生成中或不可用，请稍后重试")}
        />
        <div className="row">
          <button className="btn btn-ghost" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>上一个</button>
          <button className="btn btn-ghost" onClick={toggleMark}>
            {isMarked ? "已标记 ✓" : "标记"}
          </button>
          <button className="btn btn-ghost" onClick={() => next()}>
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
      {marksOpen && (
        <div className="source-modal" onClick={() => setMarksOpen(false)}>
          <div className="source-panel" onClick={(e) => e.stopPropagation()}>
            {marksPanel()}
          </div>
        </div>
      )}
      <CustomRangePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onConfirm={(range) => void applyCustom(range)}
      />
    </div>
  );
}
