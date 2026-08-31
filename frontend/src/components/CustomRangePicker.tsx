"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getJson } from "@/lib/api";
import type { CoverageTree } from "@/lib/types";

export interface CustomRange {
  subjects: string[];
  points: string[];
}

function TriCheck({
  checked, indeterminate, onChange,
}: {
  checked: boolean;
  indeterminate: boolean;
  onChange: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      type="checkbox"
      ref={ref}
      checked={checked}
      onChange={onChange}
      onClick={(e) => e.stopPropagation()}
    />
  );
}

function stateCounts(states: Record<string, number>, total: number) {
  const unlearned = states.new ?? 0;
  return { learned: Math.max(0, total - unlearned), unlearned };
}

function stateLabel(st: string) {
  if (st === "new") return "未学";
  if (st === "weak") return "薄弱";
  return "已学";
}

export default function CustomRangePicker({
  open, onClose, onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (range: CustomRange) => void;
}) {
  const [tree, setTree] = useState<CoverageTree | null>(null);
  const [mode, setMode] = useState<"subject" | "points" | null>(null);
  const [subjects, setSubjects] = useState<Set<string>>(new Set());
  const [points, setPoints] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    getJson<CoverageTree>("/api/coverage")
      .then((t) => { setTree(t); setError(""); })
      .catch((e) => setError(String(e)));
    setMode(null);
    setSubjects(new Set());
    setPoints(new Set());
    setExpanded(new Set());
  }, [open]);

  if (!open) return null;
  if (!mounted) return null;
  if (!tree) {
    return createPortal((
      <div className="source-modal" onClick={onClose}>
        <div className="source-panel" onClick={(e) => e.stopPropagation()}>
          <div className="ai-chat-head">
            <b>自定义学习范围</b>
            <button onClick={onClose}>×</button>
          </div>
          <div className="source-body">
            <p className="muted">{error ? `加载失败：${error}` : "加载中…"}</p>
          </div>
        </div>
      </div>
    ), document.body);
  }

  const subjectNames = Object.keys(tree);
  const allPointsOf = (subject: string): string[] =>
    Object.values(tree[subject].submodules).flatMap((sd) => Object.keys(sd.points));
  const pointsOf = (subject: string, sub: string): string[] =>
    Object.keys(tree[subject].submodules[sub].points);
  const selectedCount = mode === "subject" ? subjects.size : points.size;

  function toggleSubject(name: string) {
    setSubjects((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function togglePoint(name: string) {
    setPoints((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function toggleExpand(name: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function toggleSubjectAll(subject: string) {
    setPoints((prev) => {
      const next = new Set(prev);
      const pts = allPointsOf(subject);
      const all = pts.every((p) => next.has(p));
      pts.forEach((p) => (all ? next.delete(p) : next.add(p)));
      return next;
    });
  }

  function toggleSubAll(subject: string, sub: string) {
    setPoints((prev) => {
      const next = new Set(prev);
      const pts = pointsOf(subject, sub);
      const all = pts.every((p) => next.has(p));
      pts.forEach((p) => (all ? next.delete(p) : next.add(p)));
      return next;
    });
  }

  function confirm() {
    onConfirm(mode === "subject"
      ? { subjects: Array.from(subjects), points: [] }
      : { subjects: [], points: Array.from(points) });
  }

  return createPortal((
    <div className="source-modal" onClick={onClose}>
      <div className="source-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-chat-head">
          <b>自定义学习范围</b>
          <button onClick={onClose}>×</button>
        </div>
        <div className="source-body">
          {mode === null && (
            <div className="pick-mode">
              <p className="muted">选择学习范围的方式：</p>
              <button className="btn" onClick={() => setMode("subject")}>
                按科目选择（学整科）
              </button>
              <button className="btn" onClick={() => setMode("points")}>
                按知识点选择（勾选考点）
              </button>
            </div>
          )}
          {mode === "subject" && (
            <div className="pick-list">
              {subjectNames.map((name) => {
                const sc = stateCounts(tree[name].states, tree[name].count);
                return (
                  <label key={name} className="pick-item">
                    <input
                      type="checkbox"
                      checked={subjects.has(name)}
                      onChange={() => toggleSubject(name)}
                    />
                    <span className="pick-item-name">{name}</span>
                    <span className="muted">
                      {tree[name].count} 条 · 已学 {sc.learned} · 未学 {sc.unlearned}
                    </span>
                  </label>
                );
              })}
            </div>
          )}
          {mode === "points" && (
            <div className="pick-tree">
              {subjectNames.map((subject) => {
                const sPoints = allPointsOf(subject);
                const sChecked = sPoints.length > 0 && sPoints.every((p) => points.has(p));
                const sInd = sPoints.some((p) => points.has(p)) && !sChecked;
                const sCounts = stateCounts(tree[subject].states, tree[subject].count);
                return (
                  <div key={subject} className="pick-group">
                    <div className="pick-row pick-subject-row">
                      <TriCheck
                        checked={sChecked}
                        indeterminate={sInd}
                        onChange={() => toggleSubjectAll(subject)}
                      />
                      <button className="pick-toggle" onClick={() => toggleExpand(subject)}>
                        {expanded.has(subject) ? "▾" : "▸"} {subject}
                        <span className="muted">
                          （{tree[subject].count} 条 · 已学 {sCounts.learned} · 未学 {sCounts.unlearned}）
                        </span>
                      </button>
                    </div>
                    {expanded.has(subject) && (
                      Object.entries(tree[subject].submodules).map(([sub, sd]) => {
                        const pNames = pointsOf(subject, sub);
                        const subChecked = pNames.every((p) => points.has(p));
                        const subInd = pNames.some((p) => points.has(p)) && !subChecked;
                        const subCounts = stateCounts(sd.states, sd.count);
                        return (
                          <div key={sub} className="pick-sub">
                            <div className="pick-row">
                              <TriCheck
                                checked={subChecked}
                                indeterminate={subInd}
                                onChange={() => toggleSubAll(subject, sub)}
                              />
                              <span className="pick-sub-name">
                                {sub}（{sd.count} · 已学 {subCounts.learned} · 未学 {subCounts.unlearned}）
                              </span>
                            </div>
                            <div className="pick-points">
                              {pNames.map((p) => {
                                const st = sd.points[p];
                                return (
                                  <label key={p} className="pick-point">
                                    <input
                                      type="checkbox"
                                      checked={points.has(p)}
                                      onChange={() => togglePoint(p)}
                                    />
                                    <span className="pick-point-name">{p}</span>
                                    <span className={`pick-state st-${st}`}>{stateLabel(st)}</span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
        {mode && (
          <div className="pick-footer">
            <button className="btn" onClick={() => setMode(null)}>返回</button>
            <button
              className="btn btn-primary"
              disabled={selectedCount === 0}
              onClick={confirm}
            >
              开始学习（{selectedCount}）
            </button>
          </div>
        )}
      </div>
    </div>
  ), document.body);
}
