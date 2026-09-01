"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson, postJson } from "@/lib/api";
import { readSavedQueue, writeSavedQueue } from "@/lib/progressStore";
import type { Entry, Plan } from "@/lib/types";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";

const READ_STORE_KEY = "fakao.read.queue.v1";

export default function FlashcardView() {
  const searchParams = useSearchParams();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(0);
  const [error, setError] = useState("");
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
  const startRef = useRef(Date.now());

  useEffect(() => {
    const entryParam = searchParams.get("entry");
    const queueParam = searchParams.get("queue");
    if (queueParam === "wrong") {
      getJson<{ items: Entry[] }>("/api/wrongbook/queue?limit=30")
        .then((r) => {
          setPlan({
            date: "", quota: r.items.length, rationale: "错题重练",
            items: r.items, counts: { retry: r.items.length, review: 0, new: 0 },
          });
          setReviewedToday(new Set(r.items.filter((i) => i.reviewed_today).map((i) => i.id)));
          setCustomMode(true);
          setQueueLabel("错题重练");
          setIndex(0);
        })
        .catch((e) => setError(String(e)));
      return;
    }
    getJson<Plan>("/api/plans/today")
      .then((p) => {
        setReviewedToday(new Set(p.items.filter((i) => i.reviewed_today).map((i) => i.id)));
        if (!entryParam) {
          restoreQueue(p);
          return;
        }
        // 深链：目标条目置首，其余沿用今日计划（去重）
        getJson<Entry>(`/api/entries/${encodeURIComponent(entryParam)}`)
          .then((e) => {
            setPlan({
              date: p.date, quota: p.quota, rationale: p.rationale,
              items: [e, ...p.items.filter((i) => i.id !== e.id)],
              counts: p.counts,
            });
            setIndex(0);
          })
          .catch(() => restoreQueue(p));
      })
      .catch((e) => setError(String(e)));
  }, [searchParams]);

  // 队列位置持久化：刷新/离开后回来可恢复
  useEffect(() => {
    if (!plan || plan.items.length === 0) return;
    writeSavedQueue(READ_STORE_KEY, plan.items.map((i) => i.id), index);
  }, [plan, index]);

  function restoreQueue(p: Plan) {
    const saved = readSavedQueue(READ_STORE_KEY);
    let startIdx = 0;
    if (saved && saved.ids.length) {
      // 公共前缀：今日计划不变时精确恢复；「继续」追加的条目刷新后丢失时回退到计划末尾
      let common = 0;
      while (common < saved.ids.length && common < p.items.length &&
             saved.ids[common] === p.items[common].id) {
        common++;
      }
      if (common > 0) startIdx = Math.min(saved.idx, common);
    }
    setPlan(p);
    setIndex(startIdx);
  }

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!plan) return <p className="muted">加载中…</p>;

  const items = plan.items;
  if (items.length === 0) {
    return <div className="card"><p>今日没有条目，请先到「我的」导入数据。</p></div>;
  }
  if (index >= items.length) {
    return (
      <div className="card center">
        <h2>{queueLabel ? `${queueLabel}完成` : customMode ? "自定义范围已学完" : "今日卡片已看完"}</h2>
        <p className="muted">
          共 {items.length} 张 · 今日累计 {reviewedToday.size} 条，已记录自评。
        </p>
        {customMode ? (
          <div>
            {queueLabel ? (
              <div className="row">
                <a className="btn btn-primary" href="/study?view=wrong">回到错题本</a>
              </div>
            ) : (
              <div className="row">
                <button className="btn btn-primary" onClick={() => setPickerOpen(true)}>
                  重新选择范围
                </button>
              </div>
            )}
            {customRange && remaining > 0 ? (
              <div className="continue-box">
                <p className="muted">剩余未学 {remaining} 条，选择下一组或部分：</p>
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
                    value={continueCount}
                    onChange={(e) => setContinueCount(e.target.value)}
                  />
                  <button className="btn btn-primary" disabled={loadingMore || !continueCount}
                    onClick={() => void applyCustom(customRange, { exclude: Array.from(seenIds), limit: Number(continueCount) })}>
                    继续
                  </button>
                </div>
                {notice && <p className="muted">{notice}</p>}
              </div>
            ) : (
              <p className="muted">所选范围已全部学完，可重新选择范围继续学习。</p>
            )}
          </div>
        ) : (
          <div className="continue-box">
            <p className="muted">还想继续学？选择数量：</p>
            <div className="row">
              <button className="btn" disabled={loadingMore}
                onClick={() => void loadMore(5)}>继续 5 个</button>
              <button className="btn" disabled={loadingMore}
                onClick={() => void loadMore(10)}>继续 10 个</button>
            </div>
            <div className="continue-custom">
              <input
                type="number" min={1} max={50} placeholder="自定义数量"
                value={continueCount}
                onChange={(e) => setContinueCount(e.target.value)}
              />
              <button className="btn btn-primary" disabled={loadingMore || !continueCount}
                onClick={() => void loadMore(Number(continueCount))}>继续</button>
            </div>
          </div>
        )}
      </div>
    );
  }

  const entry: Entry = items[index];

  async function applyCustom(range: CustomRange,
                             opts?: { exclude?: string[]; limit?: number }) {
    setLoadingMore(true);
    setNotice("");
    try {
      const r = await postJson<{ items: Entry[]; total: number }>("/api/plans/custom", {
        subjects: range.subjects, points: range.points,
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

  async function rate(result: "good" | "fuzzy" | "bad") {
    if (submitting) return;
    setSubmitting(true);
    setNotice("");
    try {
      const duration = Math.round((Date.now() - startRef.current) / 1000);
      await postJson("/api/reviews", {
        entry_id: entry.id, mode: "read", result, duration_sec: duration,
      });
      startRef.current = Date.now();
      setReviewedToday((prev) => new Set(prev).add(entry.id));
      setFlipped(false);
      setDone((d) => d + 1);
      setIndex((i) => i + 1);
    } catch (e) {
      setNotice("评分保存失败，请重试：" + String(e));
    } finally {
      setSubmitting(false);
    }
  }

  function askAi() {
    window.dispatchEvent(new CustomEvent("ask-ai", {
      detail: { entry_id: entry.id, question: `讲解「${entry.point}」的要点和易错点` },
    }));
  }

  return (
    <div>
      <div className="mode-row">
        <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>
          自定义范围
        </button>
        {customMode && (
          <button className="btn btn-ghost mode-btn" onClick={() => setPickerOpen(true)}>
            重新选择
          </button>
        )}
      </div>
      {notice && <p className="muted">{notice}</p>}
      <p className="muted">
        {index + 1} / {items.length} · 本次完成 {done} 张 · 今日累计 {reviewedToday.size} 条
        {entry.read_count ? ` · 本条已看 ${entry.read_count} 次` : ""}
      </p>
      <div className={`flashcard${flipped ? " flipped" : ""}`} onClick={() => setFlipped((f) => !f)}>
        <div className="flashcard-inner">
          <div className="flashcard-face">
            <span className="tag">{entry.subject} · {entry.submodule}</span>
            <h2>
              {entry.point}
              {(entry.reviewed_today || reviewedToday.has(entry.id)) && (
                <span className="badge">今日已看</span>
              )}
            </h2>
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
                    className="chip-case"
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
          <button className="btn btn-bad" disabled={submitting}
            onClick={() => rate("bad")}>没记住</button>
          <button className="btn btn-ghost" disabled={submitting}
            onClick={() => rate("fuzzy")}>模糊</button>
          <button className="btn btn-good" disabled={submitting}
            onClick={() => rate("good")}>{submitting ? "保存中…" : "记住了"}</button>
        </div>
      )}
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
      <SourceViewer
        source={source}
        statute={statute}
        onClose={() => { setSource(null); setStatute(null); }}
      />
      <CustomRangePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onConfirm={(range) => void applyCustom(range)}
      />
    </div>
  );
}
