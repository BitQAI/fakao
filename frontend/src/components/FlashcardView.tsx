"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { delJson, getJson, postJson, putJson } from "@/lib/api";
import { readMarked, readSavedQueue, writeMarked, writeSavedQueue } from "@/lib/progressStore";
import type { Entry, MarkItem, Plan } from "@/lib/types";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import SourceViewer, { type SourceTarget } from "./SourceViewer";
import { ListenMarksPanel } from "./ListenMarksPanel";

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
  const [aiCount, setAiCount] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [marksOpen, setMarksOpen] = useState(false);
  const [marked, setMarked] = useState<MarkItem[]>([]);
  const [fPoint, setFPoint] = useState("");
  const [fAnchor, setFAnchor] = useState("");
  const [fConclusion, setFConclusion] = useState("");
  const [fPriority, setFPriority] = useState("高频考点");
  const [fNote, setFNote] = useState("");
  const [saving, setSaving] = useState(false);
  const aiCountCache = useRef<Map<string, number>>(new Map());
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

  const currentId = plan?.items[index]?.id ?? null;
  const currentIdRef = useRef<string | null>(null);
  currentIdRef.current = currentId;

  // 同一条目问过 AI 则显示历史徽标（结果缓存，进卡即查）
  useEffect(() => {
    if (!currentId) return;
    const cached = aiCountCache.current.get(currentId);
    if (cached !== undefined) { setAiCount(cached); return; }
    setAiCount(null);
    let cancelled = false;
    getJson<{ items: unknown[] }>(
      `/api/assistant/history?entry_id=${encodeURIComponent(currentId)}&limit=50`
    ).then((d) => {
      if (cancelled) return;
      aiCountCache.current.set(currentId, d.items.length);
      setAiCount(d.items.length);
    }).catch(() => { if (!cancelled) setAiCount(null); });
    return () => { cancelled = true; };
  }, [currentId]);

  // 标记：与听学共用 /api/marks（含本地旧标记迁移）
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

  // AI 问答成功后刷新徽标（AiChat 通过 ai-asked 事件通知）
  useEffect(() => {
    function handler(e: Event) {
      const id = (e as CustomEvent<{ entry_id?: string }>).detail?.entry_id;
      if (!id) return;
      const next = (aiCountCache.current.get(id) ?? 0) + 1;
      aiCountCache.current.set(id, next);
      if (currentIdRef.current === id) setAiCount(next);
    }
    window.addEventListener("ai-asked", handler);
    return () => window.removeEventListener("ai-asked", handler);
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

  const isMarked = marked.some((m) => m.entry_id === entry.id);
  async function toggleMark() {
    if (isMarked) {
      const m = marked.find((x) => x.entry_id === entry.id);
      if (!m) return;
      try {
        await delJson(`/api/marks/${m.id}`);
        setMarked((p) => p.filter((x) => x.id !== m.id));
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
  async function removeMark(m: MarkItem) {
    try {
      await delJson(`/api/marks/${m.id}`);
      setMarked((p) => p.filter((x) => x.id !== m.id));
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

  function askAi() {
    window.dispatchEvent(new CustomEvent("ask-ai", {
      detail: {
        entry_id: entry.id,
        question: `讲解「${entry.point}」的要点和易错点`,
        title: entry.point,
        description: `场景：${entry.anchor}\n结论：${entry.conclusion}`,
      },
    }));
  }

  function openEdit() {
    setFPoint(entry.point);
    setFAnchor(entry.anchor);
    setFConclusion(entry.conclusion);
    setFPriority(entry.priority);
    setFNote(entry.note ?? "");
    setNotice("");
    setEditing(true);
  }

  async function saveEdit() {
    if (saving) return;
    setSaving(true);
    setNotice("");
    try {
      const updated = await putJson<Entry>(`/api/entries/${encodeURIComponent(entry.id)}`, {
        point: fPoint.trim(), anchor: fAnchor.trim(), conclusion: fConclusion.trim(),
        priority: fPriority, note: fNote.trim() || null,
      });
      setPlan((p) => (p ? { ...p, items: p.items.map((it) => (it.id === entry.id ? { ...updated, bucket: (it as Entry).bucket } : it)) } : p));
      setEditing(false);
      setNotice("已保存更正。");
    } catch (e) {
      setNotice("保存失败：" + String(e));
    } finally {
      setSaving(false);
    }
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
        <button className="btn btn-ghost mode-btn" onClick={() => setMarksOpen(true)}>
          已标记（{marked.length}）
        </button>
      </div>
      {notice && <p className="muted">{notice}</p>}
      <p className="muted">
        {index + 1} / {items.length} · 本次完成 {done} 张 · 今日累计 {reviewedToday.size} 条
        {entry.read_count ? ` · 本条已看 ${entry.read_count} 次` : " · 本条未看"}
      </p>
      <div className={`flashcard${flipped ? " flipped" : ""}`} onClick={() => setFlipped((f) => !f)}>
        <div className="flashcard-inner">
          <div className="flashcard-face">
            <span className="tag">{entry.subject} · {entry.submodule}</span>
            <h2>
              {entry.point}
              {isMarked && (
                <span className="badge">已标记</span>
              )}
              {(entry.reviewed_today || reviewedToday.has(entry.id)) && (
                <span className="badge">今日已看</span>
              )}
              {entry.read_count ? (
                <span className="badge">已看 {entry.read_count} 次</span>
              ) : (
                <span className="badge">未看</span>
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
              问 AI{aiCount ? ` · ${aiCount}条历史` : ""}
            </button>
            <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); void toggleMark(); }}>
              {isMarked ? "已标记 ✓" : "标记"}
            </button>
            <button className="btn btn-ghost" onClick={(e) => { e.stopPropagation(); openEdit(); }}>
              编辑
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
      {editing && (
        <div className="source-modal" onClick={() => setEditing(false)}>
          <div className="source-panel" onClick={(e) => e.stopPropagation()}>
            <div className="ai-chat-head">
              <b>更正条目 · {entry.id}</b>
              <button onClick={() => setEditing(false)}>×</button>
            </div>
            <div className="source-body">
              <label className="field">标题 point
                <input value={fPoint} onChange={(e) => setFPoint(e.target.value)} maxLength={60} />
              </label>
              <label className="field">场景 anchor（{fAnchor.trim().length}/16–36 字）
                <input value={fAnchor} onChange={(e) => setFAnchor(e.target.value)} maxLength={40} />
              </label>
              <label className="field">结论 conclusion（{fConclusion.trim().length}/≤60 字，以“。”结尾）
                <input value={fConclusion} onChange={(e) => setFConclusion(e.target.value)} maxLength={70} />
              </label>
              <div className="field">优先级 priority
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {["高频考点", "易错陷阱", "新增必考", "普通"].map((p) => (
                    <button
                      key={p}
                      className={`badge-btn${fPriority === p ? "" : ""}`}
                      style={fPriority === p ? { background: "var(--primary)", color: "#fff", borderColor: "var(--primary)" } : undefined}
                      onClick={() => setFPriority(p)}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
              <label className="field">备注 note（可空）
                <input value={fNote} onChange={(e) => setFNote(e.target.value)} maxLength={100} />
              </label>
              <p className="muted" style={{ fontSize: 12 }}>仅改文本，不影响音频；法条/案例结构如需调整请走数据导入。</p>
              <div className="row">
                <button className="btn" onClick={() => setEditing(false)}>取消</button>
                <button className="btn btn-primary" disabled={saving} onClick={() => void saveEdit()}>
                  {saving ? "保存中…" : "保存"}
                </button>
              </div>
              {notice && <p className="muted">{notice}</p>}
            </div>
          </div>
        </div>
      )}
      <SourceViewer
        source={source}
        statute={statute}
        onClose={() => { setSource(null); setStatute(null); }}
      />
      {marksOpen && (
        <div className="source-modal" onClick={() => setMarksOpen(false)}>
          <div className="source-panel" onClick={(e) => e.stopPropagation()}>
            <ListenMarksPanel
              marked={marked}
              onClose={() => setMarksOpen(false)}
              onRemove={(m) => void removeMark(m)}
              onReplay={(m) => void replayMarked(m)}
              onView={viewMarked}
              onClear={() => void clearMarks()}
            />
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
