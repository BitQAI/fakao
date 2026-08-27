"use client";
import { useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import CoverageTree from "@/components/CoverageTree";
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
    const r = await postJson<Report>("/api/reports/generate/evening");
    setEvening(r);
  }

  if (error) return <p className="muted">加载失败：{error}</p>;

  const stats: Stats | null = today?.stats ?? null;
  return (
    <div className="page-box">
      <div className="segments">
        <button className={`segment${view === "review" ? " active" : ""}`} onClick={() => setView("review")}>复盘</button>
        <button className={`segment${view === "coverage" ? " active" : ""}`} onClick={() => setView("coverage")}>覆盖</button>
      </div>

      {view === "review" && (
        <>
          <section className="card">
            <h2 className="card-title">今日数据</h2>
            {stats ? (
              <p className="muted">
                完成 {stats.done}/{stats.quota}（{stats.percent}%）· 自测 {stats.quiz_correct}/{stats.quiz_total} · 听学 {stats.listen_min} 分钟 · 薄弱：{stats.weak}
              </p>
            ) : <p className="muted">暂无数据</p>}
          </section>
          {today?.morning_report && (
            <section className="card">
              <h2 className="card-title">早报</h2>
              <div className="report-content" dangerouslySetInnerHTML={{ __html: mdToHtml(today.morning_report.content) }} />
            </section>
          )}
          <section className="card">
            <h2 className="card-title">晚报</h2>
            {evening ? (
              <div className="report-content" dangerouslySetInnerHTML={{ __html: mdToHtml(evening.content) }} />
            ) : <p className="muted">今天还没生成晚报，学完后点下面按钮。</p>}
            <button className="btn btn-primary" onClick={() => void regenerate()}>
              {evening ? "重新生成晚报" : "生成晚报"}
            </button>
          </section>
        </>
      )}

      {view === "coverage" && (
        tree ? <CoverageTree tree={tree} /> : <p className="muted">加载中…</p>
      )}
    </div>
  );
}
