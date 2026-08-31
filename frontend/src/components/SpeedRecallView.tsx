"use client";
import { useEffect, useState } from "react";
import { postJson } from "@/lib/api";
import type { MarkItem } from "@/lib/types";

export default function SpeedRecallView({
  marks, onExit,
}: {
  marks: MarkItem[];
  onExit: () => void;
}) {
  const [order, setOrder] = useState<MarkItem[]>([]);
  const [idx, setIdx] = useState(0);
  const [shown, setShown] = useState(false);
  const [done, setDone] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    // 进入时随机抽点，保证不重复
    const shuffled = [...marks];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    setOrder(shuffled);
    setIdx(0); setShown(false); setDone(0);
  }, [marks]);

  async function rate(result: "good" | "fuzzy" | "bad") {
    if (submitting) return;
    const item = order[idx];
    if (!item) return;
    setSubmitting(true);
    try {
      await postJson("/api/reviews", {
        entry_id: item.entry_id, mode: "read", result, duration_sec: 0,
      });
      setShown(false);
      setDone((d) => d + 1);
      setIdx((i) => i + 1);
    } catch (e) {
      setNotice("自评保存失败：" + String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (marks.length === 0) {
    return (
      <div className="card">
        <p>没有可速记的条目，先在「听学」里标记想重背的条目。</p>
      </div>
    );
  }

  if (idx >= order.length) {
    return (
      <div className="card center">
        <h2>速记完成 🎉</h2>
        <p className="muted">本轮 {order.length} 条全部抽背完成，已记录自评。</p>
        <div className="row">
          <button className="btn btn-primary" onClick={() => { setIdx(0); setDone(0); }}>
            再来一轮
          </button>
          <button className="btn" onClick={onExit}>返回列表</button>
        </div>
      </div>
    );
  }

  const item = order[idx];
  const { entry } = item;
  return (
    <div>
      <p className="muted">
        速记 {idx + 1} / {order.length} · 已背 {done} 条
        {notice && <span className="bad">{notice}</span>}
      </p>
      <div className="card center speed-card">
        <span className="tag">{entry.subject} · {entry.submodule}</span>
        <h2>{entry.point}</h2>
        <p className="muted">{entry.anchor}</p>
        {!shown ? (
          <button className="btn btn-primary" onClick={() => setShown(true)}>
            显示结论
          </button>
        ) : (
          <>
            <div className="speed-conclusion">
              <span className="priority-badge">{entry.priority}</span>
              <h3>{entry.conclusion}</h3>
              {entry.note && <p className="note">⚠ {entry.note}</p>}
            </div>
            <div className="rate-row">
              <button className="btn btn-bad" disabled={submitting}
                onClick={() => void rate("bad")}>没记住</button>
              <button className="btn btn-ghost" disabled={submitting}
                onClick={() => void rate("fuzzy")}>模糊</button>
              <button className="btn btn-good" disabled={submitting}
                onClick={() => void rate("good")}>记住了</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
