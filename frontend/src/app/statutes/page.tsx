"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson } from "@/lib/api";
import StatuteList from "@/components/StatuteList";
import StatuteReader from "@/components/StatuteReader";
import StatuteSearchResults from "@/components/StatuteSearchResults";
import KeywordSearch from "@/components/KeywordSearch";
import type { StatuteHit, StatuteLaw } from "@/lib/statuteTypes";

function StatutesContent() {
  const params = useSearchParams();
  const lawKey = params.get("law") ?? "";
  const focusNo = Number(params.get("no") ?? "") || undefined;

  const [laws, setLaws] = useState<StatuteLaw[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [hits, setHits] = useState<StatuteHit[]>([]);
  const [searching, setSearching] = useState(false);

  const go = useCallback((next: Record<string, string | undefined>) => {
    const sp = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => { if (v) sp.set(k, v); });
    window.location.href = `/statutes${sp.toString() ? `?${sp}` : ""}`;
  }, []);

  useEffect(() => {
    getJson<{ items: StatuteLaw[] }>("/api/statutes")
      .then((d) => setLaws(d.items))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (lawKey || !query.trim()) { setHits([]); return; }
    setSearching(true);
    const timer = setTimeout(() => {
      getJson<{ items: StatuteHit[] }>(
        `/api/statute/search?q=${encodeURIComponent(query)}&limit=50`)
        .then((d) => setHits(d.items))
        .catch(() => setHits([]))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [lawKey, query]);

  if (lawKey) {
    return (
      <div className="page-box">
        <button className="btn-ghost" onClick={() => go({})}>← 返回法条库</button>
        <StatuteReader
          lawKey={lawKey}
          focusNo={focusNo}
          onPickEntry={(id) => { window.location.href = `/study?entry=${id}`; }}
        />
      </div>
    );
  }

  const kw = query.trim();
  const matchedLaws = kw
    ? laws.filter((l) => l.name.includes(kw) || l.key.includes(kw))
    : [];

  return (
    <div className="page-box">
      <h2 className="card-title">法条库</h2>
      <KeywordSearch
        value={query}
        onChange={setQuery}
        placeholder="搜法名或条文正文，如「公司法」「表见代理」"
      />
      {kw ? (
        <>
          {matchedLaws.length > 0 && (
            <>
              <p className="muted">匹配的法律（{matchedLaws.length}）</p>
              <StatuteList laws={matchedLaws} loading={false}
                onPick={(key) => go({ law: key })} />
            </>
          )}
          <StatuteSearchResults
            query={query}
            hits={hits}
            loading={searching}
            onPick={(law, no) => go({ law, no: String(no) })}
          />
        </>
      ) : (
        <StatuteList
          laws={laws}
          loading={loading}
          onPick={(key) => go({ law: key })}
        />
      )}
    </div>
  );
}

export default function StatutesPage() {
  return (
    <Suspense fallback={<p className="muted">加载中…</p>}>
      <StatutesContent />
    </Suspense>
  );
}
