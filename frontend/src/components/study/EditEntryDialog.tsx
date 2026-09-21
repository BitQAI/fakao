"use client";
import { useState } from "react";
import { putJson } from "@/lib/api";
import type { Entry } from "@/lib/types";

const PRIORITIES = ["高频考点", "易错陷阱", "新增必考", "普通"];

interface Props {
  entry: Entry;
  onSaved: (entry: Entry) => void;
  onClose: () => void;
}

/** 看背就地更正条目文本（不碰 tts / 音频）。 */
export default function EditEntryDialog({ entry, onSaved, onClose }: Props) {
  const [point, setPoint] = useState(entry.point);
  const [anchor, setAnchor] = useState(entry.anchor);
  const [conclusion, setConclusion] = useState(entry.conclusion);
  const [priority, setPriority] = useState(entry.priority);
  const [note, setNote] = useState(entry.note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      const updated = await putJson<Entry>(`/api/entries/${encodeURIComponent(entry.id)}`, {
        point: point.trim(), anchor: anchor.trim(), conclusion: conclusion.trim(),
        priority, note: note.trim() || null,
      });
      onSaved(updated);
    } catch (e) {
      setError("保存失败：" + String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="source-modal" onClick={onClose}>
      <div className="source-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-chat-head">
          <b>更正条目 · {entry.id}</b>
          <button onClick={onClose}>×</button>
        </div>
        <div className="source-body">
          <label className="field">标题 point
            <input value={point} onChange={(e) => setPoint(e.target.value)} maxLength={60} />
          </label>
          <label className="field">场景 anchor（{anchor.trim().length}/16–36 字）
            <input value={anchor} onChange={(e) => setAnchor(e.target.value)} maxLength={40} />
          </label>
          <label className="field">结论 conclusion（{conclusion.trim().length}/≤60 字，以“。”结尾）
            <input value={conclusion} onChange={(e) => setConclusion(e.target.value)} maxLength={70} />
          </label>
          <div className="field">优先级 priority
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {PRIORITIES.map((p) => (
                <button key={p} className="badge-btn"
                  style={priority === p
                    ? { background: "var(--primary)", color: "#fff", borderColor: "var(--primary)" }
                    : undefined}
                  onClick={() => setPriority(p)}>{p}</button>
              ))}
            </div>
          </div>
          <label className="field">备注 note（可空）
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={100} />
          </label>
          <p className="muted" style={{ fontSize: 12 }}>
            仅改文本，不影响音频；法条/案例结构如需调整请走数据导入。
          </p>
          <div className="row">
            <button className="btn" onClick={onClose}>取消</button>
            <button className="btn btn-primary" disabled={saving} onClick={() => void save()}>
              {saving ? "保存中…" : "保存"}
            </button>
          </div>
          {error && <p className="muted">{error}</p>}
        </div>
      </div>
    </div>
  );
}
