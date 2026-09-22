"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson } from "@/lib/api";
import CaseDocument from "@/components/CaseDocument";
import CaseLibraryList from "@/components/CaseLibraryList";
import KeywordSearch from "@/components/KeywordSearch";
import type { CaseHit, CaseStats } from "@/lib/caseLibTypes";

/** 来源筛选标签用的短名（长名在结果行里仍完整展示）。 */
const SHORT_SOURCE: Record<string, string> = {
  "人民法院案例库": "人民法院",
  "司法部案例库": "司法部",
  "最高检指导性案例": "最高检",
  "最高法指导性案例": "最高法",
};

function CasesContent() {
  const params = useSearchParams();
  const query = params.get("q") ?? "";
  const lib = params.get("lib") ?? "";
  const loc = params.get("loc") ?? "";

  const [text, setText] = useState(query);
  const [filter, setFilter] = useState("");
  const [hits, setHits] = useState<CaseHit[]>([]);
  const [stats, setStats] = useState<CaseStats | null>(null);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    getJson<CaseStats>("/api/case/stats").then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    if (lib || !text.trim()) { setHits([]); return; }
    setSearching(true);
    const timer = setTimeout(() => {
      const sp = new URLSearchParams({ q: text.trim(), limit: "30" });
      if (filter) sp.set("source", filter);
      getJson<{ items: CaseHit[] }>(`/api/case/search?${sp}`)
        .then((d) => setHits(d.items))
        .catch(() => setHits([]))
        .finally(() => setSearching(false));
    }, 350);
    return () => clearTimeout(timer);
  }, [lib, text, filter]);

  const go = useCallback((next: Record<string, string | undefined>) => {
    const sp = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => { if (v) sp.set(k, v); });
    window.location.href = `/cases${sp.toString() ? `?${sp}` : ""}`;
  }, []);

  if (lib && loc) {
    return (
      <div className="page-box">
        <button className="btn-ghost"
          onClick={() => go({ q: query || undefined })}>← 返回案例库</button>
        <CaseDocument lib={lib} loc={loc}
          onKeyword={(kw) => { setText(kw); go({ q: kw }); }} />
      </div>
    );
  }

  return (
    <div className="page-box">
      <h2 className="card-title">案例库</h2>
      <p className="muted">
        4 个来源库共 {stats ? stats.total : "…"} 篇：按标题、案号、关键词、正文模糊检索，
        点开后按正式文书分节阅读。
      </p>
      <KeywordSearch value={text} onChange={setText}
        placeholder="搜案例，如「房屋租赁」「正当防卫 必要限度」" />
      {stats && (
        <div className="caselib-filters">
          <button className={`caselib-filter${filter === "" ? " active" : ""}`}
            onClick={() => setFilter("")}>全部 {stats.total}</button>
          {stats.sources.map((s) => (
            <button key={s.source}
              className={`caselib-filter${filter === s.source ? " active" : ""}`}
              onClick={() => setFilter(s.source)}>
              {SHORT_SOURCE[s.source] ?? s.source} {s.n}
            </button>
          ))}
        </div>
      )}
      <CaseLibraryList hits={hits} query={text} loading={searching}
        onPick={(hit) => go({
          q: text.trim() || undefined, lib: hit.source, loc: hit.loc,
        })} />
    </div>
  );
}

export default function CasesPage() {
  return (
    <Suspense fallback={<p className="muted">加载中…</p>}>
      <CasesContent />
    </Suspense>
  );
}
