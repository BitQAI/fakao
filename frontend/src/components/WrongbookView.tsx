"use client";
import { useEffect, useState } from "react";
import { delJson, getJson } from "@/lib/api";
import type { MarkItem, WrongbookItem } from "@/lib/types";
import SpeedRecallView from "./SpeedRecallView";

export default function WrongbookView() {
  const [items, setItems] = useState<WrongbookItem[] | null>(null);
  const [marks, setMarks] = useState<MarkItem[]>([]);
  const [marksOpen, setMarksOpen] = useState(false);
  const [speedMode, setSpeedMode] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<{ items: WrongbookItem[] }>("/api/wrongbook?limit=200")
      .then((d) => setItems(d.items))
      .catch((e) => setError(String(e)));
    getJson<{ items: MarkItem[] }>("/api/marks")
      .then((d) => setMarks(d.items))
      .catch(() => undefined);
  }, []);

  async function removeMark(m: MarkItem) {
    try {
      await delJson(`/api/marks/${m.id}`);
      setMarks((prev) => prev.filter((x) => x.id !== m.id));
    } catch { /* 忽略 */ }
  }

  if (speedMode) {
    return (
      <div>
        <SpeedRecallView marks={marks} onExit={() => setSpeedMode(false)} />
      </div>
    );
  }

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!items) return <p className="muted">加载中…</p>;
  if (items.length === 0) {
    return (
      <div className="card">
        <p>还没有错题。做错的题、看背评「没记住」的条目会自动进入这里。</p>
        <p className="muted">去「看背」或「自测」产生第一条错题吧。</p>
      </div>
    );
  }

  return (
    <div>
      <section className="card">
        <div className="history-head">
          <b>我的标记（{marks.length}）</b>
          <button className="badge-btn" onClick={() => setMarksOpen((v) => !v)}>
            {marksOpen ? "收起" : "展开"}
          </button>
        </div>
        {marksOpen && (
          <>
            {marks.length === 0 ? (
              <p className="muted">暂无标记，听学时点「标记」收藏想重背的条目。</p>
            ) : (
              <div className="history-list">
                {marks.map((m) => (
                  <div className="card history-card" key={m.id}>
                    <div className="history-head">
                      <span className="tag">{m.entry.subject}</span>
                      <button className="badge-btn" onClick={() => void removeMark(m)}>
                        取消
                      </button>
                    </div>
                    <p className="history-stem">{m.entry.point}</p>
                    <div className="row">
                      <a className="btn" href={`/study?view=read&entry=${m.entry_id}`}>查看</a>
                      <a className="btn" href={`/study?view=listen&entry=${m.entry_id}`}>再听</a>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="row">
              <button className="btn btn-primary" disabled={marks.length === 0}
                onClick={() => setSpeedMode(true)}>
                开始速记（{marks.length}）
              </button>
            </div>
          </>
        )}
      </section>

      <div className="card center" style={{ padding: "14px" }}>
        <p className="muted">错题共 {items.length} 条，按最近错误时间排序。</p>
        <button
          className="btn btn-primary"
          onClick={() => { window.location.href = "/study?view=read&queue=wrong"; }}
        >
          开始重练（{Math.min(items.length, 30)} 条）
        </button>
      </div>
      <div className="history-list">
        {items.map((it) => (
          <div className="card history-card" key={it.id}>
            <div className="history-head">
              <span className="tag">{it.subject} · {it.submodule}</span>
              <span className="badge badge-red">错 {it.wrong_count} 次</span>
            </div>
            <p className="history-stem">{it.point}</p>
            <p className="muted">
              {it.last_wrong_ts
                ? `最近错误 ${it.last_wrong_ts.slice(0, 16).replace("T", " ")}`
                : ""}
              {it.quiz_wrong_count > 0 ? ` · 自测错 ${it.quiz_wrong_count}` : ""}
              {it.bad_count > 0 ? ` · 背评差 ${it.bad_count}` : ""}
            </p>
            <div className="row">
              <a className="btn" href={`/study?view=read&entry=${it.id}`}>再看</a>
              <a className="btn" href={`/study?view=listen&entry=${it.id}`}>再听</a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
