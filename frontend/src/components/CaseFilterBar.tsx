"use client";
import { useState } from "react";
import type { CaseFacets, CaseFilters, CaseSort } from "@/lib/caseLibTypes";

const CRIME_PREVIEW = 12;

const SORTS: { key: CaseSort; label: string }[] = [
  { key: "relevance", label: "相关度" },
  { key: "newest", label: "最新" },
  { key: "oldest", label: "最早" },
];

/** 案例库筛选条：默认只占一行（部门法 / 年份 / 排序 / 高级筛选），
 *  来源库与罪名收进「高级筛选」面板。 */
export default function CaseFilterBar({
  facets, filters, hasQuery, onChange, onReset,
}: {
  facets: CaseFacets | null;
  filters: CaseFilters;
  hasQuery: boolean;
  onChange: (patch: Partial<CaseFilters>) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [allCrimes, setAllCrimes] = useState(false);
  const advanced = (filters.source ? 1 : 0) + (filters.crime ? 1 : 0);
  const dirty = advanced > 0 || filters.field || filters.year
    || filters.sort !== "relevance";

  return (
    <div className="casebar-wrap">
      <div className="casebar">
        <select className="casebar-select" value={filters.field}
          aria-label="部门法"
          onChange={(e) => onChange({ field: e.target.value })}>
          <option value="">全部部门法</option>
          {(facets?.fields ?? []).map((f) => (
            <option key={f.value} value={f.value}>{f.value} {f.n}</option>
          ))}
        </select>
        <select className="casebar-select" value={filters.year}
          aria-label="年份"
          onChange={(e) => onChange({ year: e.target.value })}>
          <option value="">全部年份</option>
          {(facets?.years ?? []).map((y) => (
            <option key={y.value} value={y.value}>{y.value} 年</option>
          ))}
        </select>
        <select className="casebar-select" value={filters.sort}
          aria-label="排序"
          onChange={(e) => onChange({ sort: e.target.value as CaseSort })}>
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}{s.key === "relevance" && !hasQuery ? "（同最新）" : ""}
            </option>
          ))}
        </select>
        <button className={`casebar-adv${open ? " active" : ""}`}
          onClick={() => setOpen(!open)}>
          高级筛选{advanced > 0 ? ` · ${advanced}` : ""}
        </button>
      </div>

      {open && (
        <div className="casebar-panel">
          <FacetRow label="来源库">
            <Chip active={!filters.source} onClick={() => onChange({ source: "" })}>
              全部 {facets?.total ?? 0}
            </Chip>
            {(facets?.sources ?? []).map((s) => (
              <Chip key={s.value} active={filters.source === s.value}
                onClick={() => onChange({
                  source: filters.source === s.value ? "" : s.value,
                })}>
                {shortSource(s.value)} {s.n}
              </Chip>
            ))}
          </FacetRow>
          <FacetRow label="罪名">
            <Chip active={!filters.crime} onClick={() => onChange({ crime: "" })}>
              全部
            </Chip>
            {crimeList(facets, allCrimes).map((c) => (
              <Chip key={c.value} active={filters.crime === c.value}
                onClick={() => onChange({
                  crime: filters.crime === c.value ? "" : c.value,
                })}>
                {c.value} {c.n}
              </Chip>
            ))}
            {(facets?.crimes.length ?? 0) > CRIME_PREVIEW && (
              <button className="caselib-more-link" onClick={() => setAllCrimes(!allCrimes)}>
                {allCrimes ? "收起" : `展开全部 ${facets?.crimes.length} 个`}
              </button>
            )}
          </FacetRow>
          <div className="casebar-panel-foot">
            <button className="caselib-reset" disabled={!dirty} onClick={onReset}>
              清空筛选
            </button>
            <button className="caselib-more-link" onClick={() => setOpen(false)}>收起</button>
          </div>
        </div>
      )}
    </div>
  );
}

function crimeList(facets: CaseFacets | null, all: boolean) {
  const crimes = facets?.crimes ?? [];
  return all ? crimes : crimes.slice(0, CRIME_PREVIEW);
}

function FacetRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="caselib-facet-row">
      <span className="caselib-facet-label">{label}</span>
      <div className="caselib-chips">{children}</div>
    </div>
  );
}

function Chip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button className={`caselib-filter${active ? " active" : ""}`} onClick={onClick}>
      {children}
    </button>
  );
}

function shortSource(source: string) {
  return source.replace("案例库", "").replace("指导性案例", "") || source;
}
