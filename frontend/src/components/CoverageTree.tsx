"use client";
import { useState } from "react";
import KeywordSearch from "@/components/KeywordSearch";
import { searchTree, subKey } from "@/lib/pointSearch";
import type { CoverageTree as Tree } from "@/lib/types";

const STATE_COLOR: Record<string, string> = {
  new: "#9aa0a6", learned: "#2563eb", weak: "#dc2626", mastered: "#16a34a",
};
const STATE_LABEL: Record<string, string> = {
  new: "未学", learned: "已学", weak: "薄弱", mastered: "掌握",
};
// 与选择器口径一致的未看/未听标识（有数才显示）
const EXTRA: { key: "unread" | "unlistened"; label: string; color: string }[] = [
  { key: "unread", label: "未看", color: "#d97706" },
  { key: "unlistened", label: "未听", color: "#7c3aed" },
];

export default function CoverageTree({ tree }: { tree: Tree }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [keyword, setKeyword] = useState("");
  const found = searchTree(tree, keyword);

  function toggle(key: string) {
    setOpen((o) => ({ ...o, [key]: !o[key] }));
  }

  const isOpen = (key: string) => found.active || !!open[key];
  const hitPoint = (point: string) => !found.active || found.points.has(point);

  return (
    <div>
      <KeywordSearch
        value={keyword}
        onChange={setKeyword}
        placeholder="搜索科目 / 子模块 / 考点"
        hint={found.active ? `命中 ${found.total} 个考点` : null}
      />
      {found.active && found.total === 0 && <p className="muted search-empty">无匹配考点</p>}
      {Object.entries(tree).map(([subject, sdata]) => {
        if (found.active && !found.subjects.has(subject)) return null;
        return (
          <div key={subject} className="tree-subject">
            <button className="tree-row" onClick={() => toggle(subject)}>
              <span>{isOpen(subject) ? "▾" : "▸"} {subject}</span>
              <span className="state-dots">
                <span className="muted">{sdata.count} 条</span>
                {Object.entries(sdata.states).map(([s, n]) =>
                  n > 0 ? (
                    <span key={s} style={{ color: STATE_COLOR[s] }}>{STATE_LABEL[s]} {n}</span>
                  ) : null
                )}
                {EXTRA.map(({ key, label, color }) =>
                  (sdata[key] ?? 0) > 0 ? (
                    <span key={key} style={{ color }}>{label} {sdata[key]}</span>
                  ) : null
                )}
              </span>
            </button>
            {isOpen(subject) && (
              <div className="tree-children">
                {Object.entries(sdata.submodules).map(([sub, subdata]) => {
                  if (found.active && !found.subs.has(subKey(subject, sub))) return null;
                  return (
                    <div key={sub} className="tree-sub">
                      <button className="tree-row" onClick={() => toggle(sub)}>
                        <span>{isOpen(sub) ? "▾" : "▸"} {sub}</span>
                        <span className="state-dots">
                          {Object.entries(subdata.states).map(([s, n]) =>
                            n > 0 ? (
                              <span key={s} style={{ color: STATE_COLOR[s] }}>{STATE_LABEL[s]} {n}</span>
                            ) : null
                          )}
                          {EXTRA.map(({ key, label, color }) =>
                            (subdata[key] ?? 0) > 0 ? (
                              <span key={key} style={{ color }}>{label} {subdata[key]}</span>
                            ) : null
                          )}
                        </span>
                      </button>
                      {isOpen(sub) && (
                        <div className="tree-points">
                          {Object.entries(subdata.points).map(([point, pt]) =>
                            hitPoint(point) ? (
                              <span key={point} className="tree-point" style={{ color: STATE_COLOR[pt.state] }}>
                                {point}{(pt.unread ?? 0) > 0 ? " ·未看" : ""}{(pt.unlistened ?? 0) > 0 ? " ·未听" : ""}
                              </span>
                            ) : null
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
