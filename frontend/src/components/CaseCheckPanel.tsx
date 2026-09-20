"use client";
import type { CasePoint } from "@/lib/caseTypes";

interface Props {
  points: CasePoint[];
  hit: Set<number>;
  busy: boolean;
  onToggle: (no: number) => void;
  onSubmit: () => void;
}

/** 采分点勾选区：带 qno 时按小问分组（综合大案例一题十几问，平铺看不清）。 */
export default function CaseCheckPanel({
  points, hit, busy, onToggle, onSubmit,
}: Props) {
  const groups = groupByQuestion(points);
  const grouped = groups.length > 1 || (groups[0]?.qno ?? 0) > 0;
  return (
    <div className="case-check">
      <p className="hint">逐条勾选「我写到了」，没勾到的会计入未命中。</p>
      {groups.map((g) => (
        <div key={g.qno} className="check-group">
          {grouped && g.qno > 0 && <p className="point-group">第 {g.qno} 问</p>}
          {g.points.map((p) => (
            <label key={p.no} className="check-row">
              <input type="checkbox" checked={hit.has(p.no)}
                onChange={() => onToggle(p.no)} />
              <span>
                <span className="kind-badge">{p.kind}</span>
                <b>{p.no}.</b> {p.text}
                <span className="muted"> ｜{p.statutes.join("、") || "无法条"}</span>
              </span>
            </label>
          ))}
        </div>
      ))}
      <button className="btn btn-primary" disabled={busy} onClick={onSubmit}>
        {busy ? "计算中…" : "提交核对"}
      </button>
    </div>
  );
}

/** 按 qno 分组；没有 qno 的题（案例分析/论述题）合成一个无标题分组。 */
function groupByQuestion(points: CasePoint[]) {
  const map = new Map<number, CasePoint[]>();
  for (const p of points) {
    const key = p.qno ?? 0;
    map.set(key, [...(map.get(key) ?? []), p]);
  }
  return Array.from(map, ([qno, items]) => ({ qno, points: items }))
    .sort((a, b) => a.qno - b.qno);
}
