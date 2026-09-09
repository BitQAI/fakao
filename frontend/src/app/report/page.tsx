"use client";
import { useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import CoverageTree from "@/components/CoverageTree";
import HistoryView from "@/components/HistoryView";
import LeaderboardView from "@/components/LeaderboardView";
import StatsView from "@/components/StatsView";
import type { CoverageTree as Tree, Report, Stats, TodayPayload } from "@/lib/types";

export default function ReportPage() {
  const [view, setView] = useState("review");
  const [today, setToday] = useState<TodayPayload | null>(null);
  const [evening, setEvening] = useState<Report | null>(null);
  const [tree, setTree] = useState<Tree | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<TodayPayload>("/api/today").then(setToday).catch((e) => setError(String(e)));
    getJson<Report | null>("/api/reports/latest?kind=evening").then(setEvening).catch(() => undefined);
    getJson<Tree>("/api/coverage").then(setTree).catch(() => undefined);
  }, []);

  async function regenerate() {
    if (evening && !confirm("重新生成将覆盖今日复盘并消耗 token，确定？")) return;
    const r = await postJson<Report>("/api/reports/generate/evening");
    setEvening(r);
  }

  if (error) return <p className="muted">加载失败：{error}</p>;

  const stats: Stats | null = today?.stats ?? null;
  const plan = today?.plan ?? null;
  const daysLeft = today?.days_left ?? null;
  const streak = today?.streak ?? null;
  const ring = stats ? (360 * stats.percent) / 100 : 0;
  return (
    <div className="page-box">
      <div className="segments">
        <button className={`segment${view === "review" ? " active" : ""}`} onClick={() => setView("review")}>复盘</button>
        <button className={`segment${view === "coverage" ? " active" : ""}`} onClick={() => setView("coverage")}>覆盖</button>
        <button className={`segment${view === "history" ? " active" : ""}`} onClick={() => setView("history")}>历史</button>
        <button className={`segment${view === "leaderboard" ? " active" : ""}`} onClick={() => setView("leaderboard")}>排行</button>
        <button className={`segment${view === "stats" ? " active" : ""}`} onClick={() => setView("stats")}>统计</button>
      </div>

      {view === "review" && (
        <>
          <section className="card">
            <div className="page-head" style={{ marginBottom: 12 }}>
              <h1 style={{ fontSize: 20 }}>今日进度</h1>
              <span className={daysLeft !== null && daysLeft <= 17 ? "badge badge-red" : "badge"}>
                {daysLeft === null ? "未设考试日期" : `距考试 ${daysLeft} 天`}
              </span>
            </div>
            <div className="today-hero">
              <div className="progress-ring-wrap">
                <svg viewBox="0 0 44 44" className="progress-ring" role="img"
                  aria-label={`今日完成 ${stats?.percent ?? 0}%`}>
                  <circle cx="22" cy="22" r="18" className="ring-track" />
                  <circle cx="22" cy="22" r="18" className="ring-bar"
                    strokeDasharray={`${ring} 360`} />
                </svg>
                <span className="ring-text">{stats?.percent ?? 0}%</span>
              </div>
              <div className="today-hero-info">
                <p className="today-hero-title">
                  {!stats ? "暂无数据" : stats.over_done ? "超额完成 🎉" : `今日进度 ${stats.done}/${stats.quota}`}
                </p>
                {stats && (
                  <p className="muted">
                    看背+自测 {stats.done}/{stats.quota} · 听学 {stats.listen_min} 分钟{stats.weak ? ` · 薄弱：${stats.weak}` : ""}
                  </p>
                )}
                {streak && streak.current > 0 && (
                  <p className="muted stat-streak">🔥 连续学习 {streak.current} 天</p>
                )}
              </div>
            </div>
            {plan && (
              <>
                <div className="counts">
                  <div className="count"><b>{plan.counts.new}</b><span>新学</span></div>
                  <div className="count"><b>{plan.counts.review}</b><span>复习</span></div>
                  <div className="count"><b>{plan.counts.retry}</b><span>错题</span></div>
                  <div className="count">
                    <b>{stats ? `${stats.done}/${stats.quota}` : "–"}</b>
                    <span>{stats?.over_done ? "超额完成" : "看背+自测"}</span>
                  </div>
                </div>
                <div className="report-content muted" dangerouslySetInnerHTML={{ __html: mdToHtml(plan.rationale) }} />
              </>
            )}
          </section>
          <section className="card">
            <h2 className="card-title">今日复盘</h2>
            {evening ? (
              <div className="report-content" dangerouslySetInnerHTML={{ __html: mdToHtml(evening.content) }} />
            ) : <p className="muted">学完后来生成今日复盘。</p>}
            <button className="btn btn-primary" onClick={() => void regenerate()}>
              {evening ? "重新生成" : "生成今日复盘"}
            </button>
          </section>
        </>
      )}

      {view === "coverage" && (
        tree ? <CoverageTree tree={tree} /> : <p className="muted">加载中…</p>
      )}

      {view === "history" && <HistoryView />}

      {view === "leaderboard" && <LeaderboardView />}

      {view === "stats" && <StatsView />}
    </div>
  );
}
