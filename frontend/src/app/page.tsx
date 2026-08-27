"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import type { TodayPayload } from "@/lib/types";

export default function TodayPage() {
  const [data, setData] = useState<TodayPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<TodayPayload>("/api/today")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="muted">后端不可用：{error}</p>;
  if (!data) return <p className="muted">加载中…</p>;

  const { days_left, plan, stats, morning_report } = data;
  return (
    <div className="page-box">
      <header className="page-head">
        <h1>今日</h1>
        <span className={days_left !== null && days_left <= 17 ? "badge badge-red" : "badge"}>
          {days_left === null ? "未设考试日期" : `距考试 ${days_left} 天`}
        </span>
      </header>

      {morning_report && (
        <section className="card">
          <h2 className="card-title">早报</h2>
          <div className="report-content" dangerouslySetInnerHTML={{ __html: mdToHtml(morning_report.content) }} />
        </section>
      )}

      <section className="card">
        <h2 className="card-title">今日计划</h2>
        <div className="counts">
          <div className="count"><b>{plan.counts.new}</b><span>新学</span></div>
          <div className="count"><b>{plan.counts.review}</b><span>复习</span></div>
          <div className="count"><b>{plan.counts.retry}</b><span>错题</span></div>
          <div className="count"><b>{stats.done}/{stats.quota}</b><span>已完成</span></div>
        </div>
        <p className="muted">{plan.rationale}</p>
      </section>

      <section className="quick-actions">
        <Link className="btn btn-primary" href="/study?view=read">看背</Link>
        <Link className="btn btn-primary" href="/study?view=listen">听学</Link>
        <Link className="btn btn-primary" href="/study?view=quiz">自测</Link>
      </section>
    </div>
  );
}
