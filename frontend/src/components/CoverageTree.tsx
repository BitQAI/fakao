"use client";
import { useState } from "react";
import type { CoverageTree as Tree } from "@/lib/types";

const STATE_COLOR: Record<string, string> = {
  new: "#9aa0a6", learned: "#2563eb", weak: "#dc2626", mastered: "#16a34a",
};
const STATE_LABEL: Record<string, string> = {
  new: "未学", learned: "已学", weak: "薄弱", mastered: "掌握",
};

export default function CoverageTree({ tree }: { tree: Tree }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  function toggle(key: string) {
    setOpen((o) => ({ ...o, [key]: !o[key] }));
  }

  return (
    <div>
      {Object.entries(tree).map(([subject, sdata]) => (
        <div key={subject} className="tree-subject">
          <button className="tree-row" onClick={() => toggle(subject)}>
            <span>{open[subject] ? "▾" : "▸"} {subject}</span>
            <span className="muted">{sdata.count} 条</span>
          </button>
          {open[subject] && (
            <div className="tree-children">
              {Object.entries(sdata.submodules).map(([sub, subdata]) => (
                <div key={sub} className="tree-sub">
                  <button className="tree-row" onClick={() => toggle(sub)}>
                    <span>{open[sub] ? "▾" : "▸"} {sub}</span>
                    <span className="state-dots">
                      {Object.entries(subdata.states).map(([s, n]) =>
                        n > 0 ? (
                          <span key={s} style={{ color: STATE_COLOR[s] }}>{STATE_LABEL[s]} {n}</span>
                        ) : null
                      )}
                    </span>
                  </button>
                  {open[sub] && (
                    <div className="tree-points">
                      {Object.entries(subdata.points).map(([point, pt]) => (
                        <span key={point} className="tree-point" style={{ color: STATE_COLOR[pt.state] }}>
                          {point}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
