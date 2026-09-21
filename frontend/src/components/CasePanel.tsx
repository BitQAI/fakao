"use client";
import { useState } from "react";
import type { CaseQType } from "@/lib/caseTypes";
import CaseView from "./CaseView";
import CaseReview from "./CaseReview";

const TABS: { key: CaseQType | "review"; label: string }[] = [
  { key: "case", label: "今日案例" },
  { key: "essay", label: "论述题" },
  { key: "composite", label: "综合大案例" },
  { key: "review", label: "复盘池" },
];

/** 主观题模块：案例分析 / 论述题（第1题）/ 综合大案例（第4题）/ 复盘池。 */
export default function CasePanel() {
  const [tab, setTab] = useState<CaseQType | "review">("case");
  return (
    <div>
      <div className="segments" style={{ marginBottom: 10 }}>
        {TABS.map((t) => (
          <button key={t.key} className={`segment${tab === t.key ? " active" : ""}`}
            onClick={() => setTab(t.key)}>{t.label}</button>
        ))}
      </div>
      {tab === "review" ? <CaseReview /> : <CaseView type={tab} key={tab} />}
    </div>
  );
}
