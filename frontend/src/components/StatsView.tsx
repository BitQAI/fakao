"use client";
import { useEffect, useMemo, useState } from "react";
import { getJson } from "@/lib/api";
import type { StatsOverview } from "@/lib/types";

const MASTERY_LABEL: Record<string, string> = {
  new: "未学", learned: "已学", weak: "薄弱", mastered: "掌握",
};

function LineChart({ daily }: { daily: StatsOverview["daily"] }) {
  const recent = daily.slice(-14);
  const totals = recent.map((d) => d.read + d.listen + d.quiz);
  const max = Math.max(...totals, 1);
  const W = 300, H = 84, P = 6;
  const pts = totals.map((v, i) => {
    const x = P + (i * (W - P * 2)) / Math.max(recent.length - 1, 1);
    const y = H - P - (v / max) * (H - P * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  if (!recent.length) return <p className="muted">暂无数据</p>;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
      aria-label="近14天学习量">
      <defs>
        <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--primary)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon points={`${P},${H - P} ${pts} ${W - P},${H - P}`} fill="url(#chartFill)" />
      <polyline points={pts} fill="none" stroke="var(--primary)" strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round" />
      {totals.map((v, i) => (
        <circle key={i} cx={P + (i * (W - P * 2)) / Math.max(recent.length - 1, 1)}
          cy={H - P - (v / max) * (H - P * 2)} r="2.4" fill="var(--primary)" />
      ))}
    </svg>
  );
}

function Heatmap({ daily }: { daily: StatsOverview["daily"] }) {
  const byDate = useMemo(() => {
    const m: Record<string, number> = {};
    for (const d of daily) m[d.date] = d.read + d.listen + d.quiz;
    return m;
  }, [daily]);
  const cells = useMemo(() => {
    const out: { date: Date; level: number }[] = [];
    const end = new Date();
    end.setHours(0, 0, 0, 0);
    const start = new Date(end);
    start.setDate(start.getDate() - 83);
    const offset = (start.getDay() + 6) % 7;
    start.setDate(start.getDate() - offset);
    for (let i = 0; i < 84 + offset; i++) {
      const d = new Date(start);
      d.setDate(d.getDate() + i);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      out.push({ date: d, level: Math.min(byDate[key] ?? 0, 5) });
    }
    return out;
  }, [byDate]);
  const weeks: typeof cells[] = [];
  for (let w = 0; w < cells.length / 7; w++) weeks.push(cells.slice(w * 7, w * 7 + 7));
  return (
    <div className="heatmap">
      {weeks.map((week, wi) => (
        <div className="heatmap-col" key={wi}>
          {week.map((c, ri) => (
            <div
              key={ri}
              className={`heat-cell heat-${c.level}`}
              title={`${c.date.getFullYear()}-${String(c.date.getMonth() + 1).padStart(2, "0")}-${String(c.date.getDate()).padStart(2, "0")}`}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export default function StatsView() {
  const [data, setData] = useState<StatsOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<StatsOverview>("/api/stats/overview?days=90")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!data) return <p className="muted">加载中…</p>;
  const { totals, mastery, streak } = data;
  const total = (mastery.new ?? 0) + (mastery.learned ?? 0)
    + (mastery.weak ?? 0) + (mastery.mastered ?? 0);
  return (
    <div>
      <section className="card center">
        <p className="stat-streak">
          🔥 连续学习 <b>{streak.current}</b> 天
          <span className="muted"> · 最长 {streak.longest} 天</span>
        </p>
        <div className="counts">
          <div className="count"><b>{totals.read}</b><span>看背</span></div>
          <div className="count"><b>{totals.listen}</b><span>听学</span></div>
          <div className="count"><b>{totals.quiz}</b><span>自测</span></div>
          <div className="count"><b>{totals.minutes}</b><span>分钟</span></div>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">掌握度分布</h2>
        <div className="mastery-chips">
          {Object.entries(MASTERY_LABEL).map(([k, label]) => (
            <span key={k} className={`mastery-chip st-${k}`}>
              {label} {mastery[k] ?? 0}
            </span>
          ))}
          <span className="muted">共 {total} 条</span>
        </div>
      </section>

      <section className="card">
        <h2 className="card-title">近 14 天学习量</h2>
        <LineChart daily={data.daily} />
      </section>

      <section className="card">
        <h2 className="card-title">近 12 周打卡热力图</h2>
        <Heatmap daily={data.daily} />
        <p className="muted">颜色越深当日学习越多；连续天数统计看/听/测任一模态。</p>
      </section>
    </div>
  );
}
