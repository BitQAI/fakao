"use client";
import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { useAiShortcut } from "@/lib/aiShortcut";
import type { CaseRef, Entry, MarkItem, Plan } from "@/lib/types";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";
import { ListenMarksPanel } from "./ListenMarksPanel";
import CardFace from "./study/CardFace";
import EditEntryDialog from "./study/EditEntryDialog";
import EntryFace from "./study/EntryFace";
import ReadFinishCard from "./study/ReadFinishCard";
import { useReadPlan } from "./study/useReadPlan";
import { useStudyMarks } from "./study/useStudyMarks";

/** 看背：一个混合队列（正式条目 + 法条题卡），两种卡共用同一套外壳、徽章与三档自评。 */
export default function FlashcardView() {
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(0);
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reviewedToday, setReviewedToday] = useState<Set<string>>(new Set());
  const [continueCount, setContinueCount] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [customMode, setCustomMode] = useState(false);
  const [queueLabel, setQueueLabel] = useState("");
  const [customRange, setCustomRange] = useState<CustomRange | null>(null);
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set());
  const [remaining, setRemaining] = useState(0);
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [statute, setStatute] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [marksOpen, setMarksOpen] = useState(false);
  const startRef = useRef(Date.now());
  const marks = useStudyMarks();
  const { plan, setPlan, index, setIndex, error, setError } = useReadPlan({
    onPlan: (p) => setReviewedToday(
      new Set(p.items.filter((i) => i.reviewed_today).map((i) => i.id))),
    onWrongQueue: (items) => {
      setPlan({
        date: "", quota: items.length, rationale: "错题重练",
        items, counts: { retry: items.length, review: 0, new: 0 },
      });
      setReviewedToday(new Set(items.filter((i) => i.reviewed_today).map((i) => i.id)));
      setCustomMode(true);
      setQueueLabel("错题重练");
    },
  });

  // 问 AI 快捷入口 + 历史条数徽标（与听学共用）
  const { askAi, aiLabel } = useAiShortcut(plan?.items[index] ?? null);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!plan) return <p className="muted">加载中…</p>;

  const items = plan.items;
  if (items.length === 0) {
    return <div className="card"><p>今日没有条目，请先到「我的」导入数据。</p></div>;
  }
  const entry = items[index];

  async function rate(result: "good" | "fuzzy" | "bad") {
    if (submitting || !entry) return;
    setSubmitting(true);
    setNotice("");
    try {
      const duration = Math.round((Date.now() - startRef.current) / 1000);
      await postJson("/api/reviews", {
        entry_id: entry.id, mode: "read", result, duration_sec: duration,
      });
      startRef.current = Date.now();
      setReviewedToday((prev) => new Set(prev).add(entry.id));
      setPlan((p) => (p ? {
        ...p,
        items: p.items.map((it) => (it.id === entry.id
          ? { ...it, read_count: (it.read_count || 0) + 1, reviewed_today: true }
          : it)),
      } : p));
      setFlipped(false);
      setDone((d) => d + 1);
      setIndex((i) => i + 1);
    } catch (e) {
      setNotice("评分保存失败，请重试：" + String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function applyCustom(range: CustomRange,
                             opts?: { exclude?: string[]; limit?: number }) {
    setLoadingMore(true);
    setNotice("");
    try {
      const r = await postJson<{ items: Entry[]; total: number }>("/api/plans/custom", {
        subjects: range.subjects, points: range.points,
        kinds: range.kinds ?? [], laws: range.laws ?? [],
        limit: opts?.limit ?? 200,
        exclude: opts?.exclude ?? [],
      });
      if (!r.items.length) {
        if (opts?.exclude?.length) setRemaining(0);
        setNotice(opts?.exclude?.length
          ? "剩余已全部学完。"
          : "所选范围暂无条目，请重新选择。");
        return;
      }
      setPlan({
        date: "", quota: r.items.length, rationale: "自定义范围",
        items: r.items, counts: { retry: 0, review: 0, new: r.items.length },
      });
      // 并行拉取今日已读记录，合并入 reviewedToday 以便刷新后恢复进度
      getJson<{ items: { entry_id: string; ts: string }[] }>("/api/reviews/history?mode=read&limit=500")
        .then((d) => {
          const today = new Date().toISOString().slice(0, 10);
          const todayIds = Array.from(new Set(d.items.filter((it) => it.ts.startsWith(today)).map((it) => it.entry_id)));
          const newIds = r.items.filter((i) => i.reviewed_today).map((i) => i.id);
          setReviewedToday(new Set([...todayIds, ...newIds]));
        })
        .catch(() => setReviewedToday(new Set(r.items.filter((i) => i.reviewed_today).map((i) => i.id))));
      setSeenIds(new Set([...(opts?.exclude ?? []), ...r.items.map((i) => i.id)]));
      setRemaining(Math.max(0, r.total - r.items.length));
      setCustomRange(range);
      setIndex(0);
      setDone(0);
      setFlipped(false);
      setCustomMode(true);
      setQueueLabel("");
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
    try {
      const r = await postJson<{ items: Entry[] }>("/api/plans/continue", { count });
      if (!r.items.length) return;
      setPlan((p) => (p ? { ...p, items: [...p.items, ...r.items] } : p));
      setReviewedToday((prev) => {
        const next = new Set(prev);
        r.items.forEach((it) => { if (it.reviewed_today) next.add(it.id); });
        return next;
      });
      setIndex(items.length);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingMore(false);
      setContinueCount("");
    }
  }

  // 重背：队列内直接跳卡，不在队列则取回置首
  async function replayMarked(m: MarkItem) {
    setNotice("");
    if (!plan) return;
    const inIdx = plan.items.findIndex((i) => i.id === m.entry_id);
    if (inIdx >= 0) {
      setFlipped(false);
      setIndex(inIdx);
    } else {
      try {
        const e = await getJson<Entry>(`/api/entries/${encodeURIComponent(m.entry_id)}`);
        setPlan((p) => (p ? { ...p, items: [e, ...p.items.filter((i) => i.id !== e.id)] } : p));
        setFlipped(false);
        setIndex(0);
      } catch {
        setNotice("重背失败：条目不存在或已下架。");
        return;
      }
    }
    setMarksOpen(false);
  }

  function viewMarked(m: MarkItem) {
    window.location.href = `/study?view=read&entry=${encodeURIComponent(m.entry_id)}`;
  }

  const marksPanel = marksOpen && (
    <div className="source-modal" onClick={() => setMarksOpen(false)}>
      <div className="source-panel" onClick={(e) => e.stopPropagation()}>
        <ListenMarksPanel marked={marks.marked} onClose={() => setMarksOpen(false)}
          onRemove={(m) => void marks.removeMark(m)}
          onReplay={(m) => void replayMarked(m)}
          onView={viewMarked} onClear={() => void marks.clearMarks()} />
      </div>
    </div>
  );

  if (index >= items.length) {
    return (
      <div className="page-box">
        <ReadFinishCard
          customMode={customMode} queueLabel={queueLabel}
          itemsCount={items.length} reviewedCount={reviewedToday.size}
          remaining={remaining} loadingMore={loadingMore}
          continueCount={continueCount} notice={notice || marks.error}
          onCountChange={setContinueCount}
          onPickRange={() => setPickerOpen(true)}
          onContinueRange={(limit) => {
            if (customRange) {
              void applyCustom(customRange, { exclude: Array.from(seenIds), limit });
            }
          }}
          onLoadMore={(count) => void loadMore(count)}
        />
        <SourceViewer source={source} statute={statute}
          onClose={() => { setSource(null); setStatute(null); }} />
        {marksPanel}
        <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)}
          onConfirm={(range) => void applyCustom(range)} />
      </div>
    );
  }

  const isCard = entry.kind === "card";
  const isMarked = Boolean(marks.markOf(entry.id));
  const shared = {
    entry,
    flipped,
    onFlip: () => setFlipped((f) => !f),
    isMarked,
    reviewedToday: reviewedToday.has(entry.id),
    aiLabel,
    submitting,
    onRate: (r: "good" | "fuzzy" | "bad") => void rate(r),
    onAskAi: askAi,
    onToggleMark: () => void marks.toggleMark(entry.id),
    onStatute: (s: string) => setStatute(s),
  };

  return (
    <div>
      <div className="mode-row">
        <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>
          {customMode ? "重新选择" : "自定义范围"}
        </button>
        <button className="btn btn-ghost mode-btn" onClick={() => setMarksOpen(true)}>
          已标记（{marks.marked.length}）
        </button>
      </div>
      {(notice || marks.error) && <p className="muted">{notice || marks.error}</p>}
      <p className="muted">
        {index + 1} / {items.length} · 本次完成 {done} 张 · 今日累计 {reviewedToday.size} 条
        {entry.read_count ? ` · 本条已看 ${entry.read_count} 次` : " · 本条未看"}
      </p>
      {isCard
        ? <CardFace {...shared} />
        : <EntryFace {...shared} onEdit={() => setEditing(true)}
            onCase={(c: CaseRef) => setSource({ kind: "case", ref: c.source, loc: c.loc })} />}
      <div className="row">
        <button className="btn btn-ghost" disabled={index === 0 || submitting}
          onClick={() => {
            setFlipped(false);
            startRef.current = Date.now();
            setIndex((i) => Math.max(0, i - 1));
          }}>
          上一个
        </button>
        <button className="btn btn-ghost" disabled={submitting}
          onClick={() => {
            setFlipped(false);
            startRef.current = Date.now();
            setIndex((i) => Math.min(items.length, i + 1));
          }}>
          下一个
        </button>
      </div>
      {editing && !isCard && (
        <EditEntryDialog entry={entry} onClose={() => setEditing(false)}
          onSaved={(updated) => {
            setPlan((p) => (p ? {
              ...p,
              items: p.items.map((it) => (it.id === updated.id
                ? { ...updated, bucket: it.bucket } : it)),
            } : p));
            setEditing(false);
            setNotice("已保存更正。");
          }} />
      )}
      <SourceViewer source={source} statute={statute}
        onClose={() => { setSource(null); setStatute(null); }} />
      {marksPanel}
      <CustomRangePicker open={pickerOpen} onClose={() => setPickerOpen(false)}
        onConfirm={(range) => void applyCustom(range)} />
    </div>
  );
}
