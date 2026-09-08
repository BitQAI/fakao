"use client";
import type { MarkItem } from "@/lib/types";

export function ListenMarksPanel({
  marked,
  onClose,
  onRemove,
  onReplay,
  onView,
  onClear,
}: {
  marked: MarkItem[];
  onClose: () => void;
  onRemove: (m: MarkItem) => void;
  onReplay: (m: MarkItem) => void;
  onView: (m: MarkItem) => void;
  onClear: () => void;
}) {
  return (
    <>
      <div className="ai-chat-head">
        <b>已标记条目（{marked.length}）</b>
        <button onClick={onClose}>×</button>
      </div>
      <div className="source-body">
        {marked.length === 0 ? (
          <p className="muted">暂无标记。看背或听学时点「标记」收藏想重背的条目。</p>
        ) : (
          <div className="history-list">
            {marked.map((m) => (
              <div key={m.id} className="card history-card">
                <div className="history-head">
                  <span className="tag">{m.entry.subject}</span>
                  <button className="badge-btn" onClick={() => onRemove(m)}>取消标记</button>
                </div>
                <p className="history-stem">{m.entry.point}</p>
                <div className="row">
                  <button className="btn" onClick={() => onReplay(m)}>重背</button>
                  <button className="btn btn-primary" onClick={() => onView(m)}>查看</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {marked.length > 0 && (
        <div className="pick-footer">
          <button className="btn" onClick={onClear}>清空标记</button>
        </div>
      )}
    </>
  );
}
