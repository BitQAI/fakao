"use client";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson } from "@/lib/api";
import CaseFilterBar from "@/components/CaseFilterBar";
import CaseHistoryPanel from "@/components/CaseHistoryPanel";
import CaseLibraryList from "@/components/CaseLibraryList";
import CaseReader from "@/components/CaseReader";
import KeywordSearch from "@/components/KeywordSearch";
import {
  EMPTY_READER_CONTEXT, filtersFromParams, listPath, readerContextFromParams,
  readerPath, searchPath,
} from "@/lib/caseNav";
import { DEFAULT_CASE_SORT } from "@/lib/caseLibTypes";
import type { CaseFacets, CaseFilters, CaseHit, CaseSearchResult } from "@/lib/caseLibTypes";

const PAGE = 30;
const DEFAULT_FILTERS: CaseFilters = {
  source: "", field: "", crime: "", year: "", viewed: "", sort: DEFAULT_CASE_SORT,
};

function CasesContent() {
  const params = useSearchParams();
  const lib = params.get("lib") ?? "";
  const loc = params.get("loc") ?? "";

  const [text, setText] = useState(() => params.get("q") ?? "");
  // 筛选从 URL 初始化：从阅读视图返回时保留刚才的检索条件
  const [filters, setFilters] = useState<CaseFilters>(() => filtersFromParams(params));
  const [facets, setFacets] = useState<CaseFacets | null>(null);
  const [hits, setHits] = useState<CaseHit[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  /** 阅读上下文（检索词 + 筛选）：阅读视图算前后篇、返回列表还原筛选都靠它。 */
  const context = useMemo(() => readerContextFromParams(params), [params]);
  const go = useCallback((path: string) => { window.location.href = path; }, []);
  const openCase = useCallback(
    (source: string, target: string) =>
      go(readerPath({ q: text, ...filters }, source, target)),
    [go, text, filters]);

  useEffect(() => {
    getJson<CaseFacets>("/api/case/facets").then(setFacets).catch(() => setFacets(null));
  }, []);

  // 关键词或筛选变化 → 从第一页重新取
  useEffect(() => {
    if (lib) return;
    const mine = ++seq.current;
    setLoading(true);
    const timer = setTimeout(() => {
      getJson<CaseSearchResult>(searchPath(text, filters, 0, PAGE))
        .then((d) => {
          if (mine !== seq.current) return;
          setHits(d.items);
          setTotal(d.total);
        })
        .catch(() => { if (mine === seq.current) { setHits([]); setTotal(0); } })
        .finally(() => { if (mine === seq.current) setLoading(false); });
    }, 300);
    return () => clearTimeout(timer);
  }, [lib, text, filters]);

  const loadMore = useCallback(() => {
    const mine = seq.current;
    setLoading(true);
    getJson<CaseSearchResult>(searchPath(text, filters, hits.length, PAGE))
      .then((d) => {
        if (mine !== seq.current) return;
        setHits((prev) => [...prev, ...d.items]);
        setTotal(d.total);
      })
      .finally(() => { if (mine === seq.current) setLoading(false); });
  }, [text, filters, hits.length]);

  if (lib && loc) {
    return (
      <div className="page-box">
        <CaseReader lib={lib} loc={loc} context={context}
          onBack={() => go(listPath(context.q, context))}
          onOpen={openCase}
          onKeyword={(kw) => go(listPath(kw, filters))} />
      </div>
    );
  }

  return (
    <div className="page-box">
      <h2 className="card-title">案例库</h2>
      <p className="muted">
        {facets ? `4 个来源库共 ${facets.total} 篇：` : "4 个来源库："}
        默认先看没读过的；可按部门法、罪名、年份筛选后直接翻，也可以输关键词检索。
      </p>
      <KeywordSearch value={text} onChange={setText}
        placeholder="搜案例，如「房屋租赁」「正当防卫 必要限度」" />
      <CaseFilterBar
        facets={facets}
        filters={filters}
        hasQuery={text.trim().length > 0}
        onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
        onReset={() => setFilters(DEFAULT_FILTERS)}
      />
      <CaseHistoryPanel
        onOpen={(source, target) =>
          go(readerPath(EMPTY_READER_CONTEXT, source, target))} />
      <CaseLibraryList
        hits={hits}
        query={text}
        loading={loading}
        total={total}
        summary={summaryOf(filters)}
        onPick={(hit) => openCase(hit.source, hit.loc)}
        onLoadMore={loadMore}
      />
    </div>
  );
}

/** 结果计数行里带上当前筛选摘要（不额外占一行）。 */
function summaryOf(filters: CaseFilters) {
  return [filters.field, filters.crime, filters.year && `${filters.year} 年`,
          filters.source,
          filters.viewed === "no" ? "只看未看过"
            : filters.viewed === "yes" ? "只看已看过" : "",
          filters.sort === "unviewed" ? "未看过优先"
            : filters.sort === "newest" ? "最新在前"
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
