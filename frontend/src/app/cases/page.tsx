"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson } from "@/lib/api";
import CaseDocument from "@/components/CaseDocument";
import CaseFilterBar from "@/components/CaseFilterBar";
import CaseLibraryList from "@/components/CaseLibraryList";
import KeywordSearch from "@/components/KeywordSearch";
import type {
  CaseFacets, CaseFilters, CaseHit, CaseSearchResult,
} from "@/lib/caseLibTypes";

const PAGE = 30;
const EMPTY_FILTERS: CaseFilters = {
  source: "", field: "", crime: "", year: "", sort: "relevance",
};

function CasesContent() {
  const params = useSearchParams();
  const query = params.get("q") ?? "";
  const lib = params.get("lib") ?? "";
  const loc = params.get("loc") ?? "";

  const [text, setText] = useState(query);
  const [filters, setFilters] = useState<CaseFilters>(EMPTY_FILTERS);
  const [facets, setFacets] = useState<CaseFacets | null>(null);
  const [hits, setHits] = useState<CaseHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    getJson<CaseFacets>("/api/case/facets").then(setFacets).catch(() => setFacets(null));
  }, []);

  const url = useCallback((offset: number) => {
    const sp = new URLSearchParams({
      limit: String(PAGE), offset: String(offset), sort: filters.sort,
    });
    if (text.trim()) sp.set("q", text.trim());
    if (filters.source) sp.set("source", filters.source);
    if (filters.field) sp.set("field", filters.field);
    if (filters.crime) sp.set("crime", filters.crime);
    if (filters.year) sp.set("year", filters.year);
    return `/api/case/search?${sp}`;
  }, [text, filters]);

  // 关键词或筛选变化 → 从第一页重新取
  useEffect(() => {
    if (lib) return;
    const mine = ++seq.current;
    setLoading(true);
    const timer = setTimeout(() => {
      getJson<CaseSearchResult>(url(0))
        .then((d) => {
          if (mine !== seq.current) return;
          setHits(d.items);
          setTotal(d.total);
        })
        .catch(() => { if (mine === seq.current) { setHits([]); setTotal(0); } })
        .finally(() => { if (mine === seq.current) setLoading(false); });
    }, 300);
    return () => clearTimeout(timer);
  }, [lib, url]);

  const loadMore = useCallback(() => {
    const mine = seq.current;
    setLoading(true);
    getJson<CaseSearchResult>(url(hits.length))
      .then((d) => {
        if (mine !== seq.current) return;
        setHits((prev) => [...prev, ...d.items]);
        setTotal(d.total);
      })
      .finally(() => { if (mine === seq.current) setLoading(false); });
  }, [hits.length, url]);

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
        {facets ? `4 个来源库共 ${facets.total} 篇：` : "4 个来源库："}
        可按部门法、罪名、年份筛选后直接翻，也可以输关键词检索。
      </p>
      <KeywordSearch value={text} onChange={setText}
        placeholder="搜案例，如「房屋租赁」「正当防卫 必要限度」" />
      <CaseFilterBar
        facets={facets}
        filters={filters}
        hasQuery={text.trim().length > 0}
        onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
        onReset={() => setFilters(EMPTY_FILTERS)}
      />
      <CaseLibraryList
        hits={hits}
        query={text}
        loading={loading}
        total={total}
        summary={summaryOf(filters)}
        onPick={(hit) => go({
          q: text.trim() || undefined, lib: hit.source, loc: hit.loc,
        })}
        onLoadMore={loadMore}
      />
    </div>
  );
}

/** 结果计数行里带上当前筛选摘要（不额外占一行）。 */
function summaryOf(filters: CaseFilters) {
  return [filters.field, filters.crime, filters.year && `${filters.year} 年`,
          filters.source, filters.sort === "newest" ? "最新在前"
            : filters.sort === "oldest" ? "最早在前" : ""]
    .filter(Boolean).join(" · ");
}

export default function CasesPage() {
  return (
    <Suspense fallback={<p className="muted">加载中…</p>}>
      <CasesContent />
    </Suspense>
  );
}
