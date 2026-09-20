"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson } from "@/lib/api";
import type {
  StatuteArticle, StatuteEntryRef, StatuteLawPayload,
} from "@/lib/statuteTypes";

/** 条文渲染：编/章/节分组、款分行、项缩进、条号双显、展开看反向索引。 */
export default function StatuteReader({
  lawKey, focusNo, onPickEntry,
}: {
  lawKey: string;
  focusNo?: number;
  onPickEntry: (entryId: string) => void;
}) {
  const [data, setData] = useState<StatuteLawPayload | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError("");
    setOpen(null);
    getJson<StatuteLawPayload>(
      `/api/statutes/${encodeURIComponent(lawKey)}?limit=1000`,
    )
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [lawKey]);

  useEffect(() => {
    if (!data || !focusNo) return;
    const target = data.items.find((a) => a.no === focusNo);
    if (!target) return;
    setOpen(anchorId(lawKey, target));
    setTimeout(() => {
      document.getElementById(anchorId(lawKey, target))
        ?.scrollIntoView({ block: "center" });
    }, 80);
  }, [data, focusNo, lawKey]);

  const groups = useMemo(() => groupByChapter(data?.items ?? []), [data]);

  if (error) {
    const missing = error.includes("404");
    return (
      <p className="bad">
        {missing ? "法条库暂未收录这部法律（等正文投递入库后即可查看）。"
                 : `加载失败：${error}`}
      </p>
    );
  }
  if (!data) return <p className="muted">加载中…</p>;

  return (
    <div className="statute-reader">
      <div className="statute-head">
        <b>{data.name}</b>
        <span className="muted">共 {data.total} 条</span>
      </div>
      {metaLine(data.meta) && <p className="hint">{metaLine(data.meta)}</p>}
      {groups.map((group) => (
        <div key={group.title}>
          {group.title && <div className="statute-chapter">{group.title}</div>}
          {group.items.map((art) => (
            <ArticleRow
              key={anchorId(lawKey, art)}
              lawKey={lawKey}
              art={art}
              expanded={open === anchorId(lawKey, art)}
              onToggle={() => setOpen(
                open === anchorId(lawKey, art) ? null : anchorId(lawKey, art))}
              onPickEntry={onPickEntry}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function ArticleRow({
  lawKey, art, expanded, onToggle, onPickEntry,
}: {
  lawKey: string;
  art: StatuteArticle;
  expanded: boolean;
  onToggle: () => void;
  onPickEntry: (entryId: string) => void;
}) {
  const [refs, setRefs] = useState<StatuteEntryRef[] | null>(null);
  const loadRefs = useCallback(() => {
    if (refs) return;
    getJson<{ items: StatuteEntryRef[] }>(
      `/api/statute/entries?law=${encodeURIComponent(lawKey)}&no=${art.no}`,
    ).then((d) => setRefs(d.items)).catch(() => setRefs([]));
  }, [art.no, lawKey, refs]);

  useEffect(() => {
    if (expanded) loadRefs();
  }, [expanded, loadRefs]);

  const lines = art.text.split("\n").filter((l) => l.trim());
  return (
    <div className="statute-item" id={anchorId(lawKey, art)}>
      <button className="statute-item-head" onClick={onToggle}>
        <span className="statute-no">{art.label}</span>
        <span className="statute-no-arabic">{art.no}</span>
        <span className="statute-preview">{lines[0]}</span>
      </button>
      {expanded && (
        <div className="statute-body">
          {lines.map((line, i) => (
            <p key={i} className={isItem(line) ? "statute-line-item" : "statute-line"}>
              {line}
            </p>
          ))}
          <div className="statute-refs">
            <span className="muted">
              引用该条的考点：{refs === null ? "查询中…" : `${refs.length} 条`}
            </span>
            {refs?.map((ref) => (
              <button key={ref.id} className="chip" onClick={() => onPickEntry(ref.id)}>
                {ref.subject}｜{ref.point}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function anchorId(lawKey: string, art: StatuteArticle) {
  return `${lawKey}-${art.label}`;
}

function isItem(line: string) {
  return /^[（(][一二三四五六七八九十\d]+[）)]/.test(line);
}

function groupByChapter(items: StatuteArticle[]) {
  const groups: { title: string; items: StatuteArticle[] }[] = [];
  for (const art of items) {
    const title = art.chapter.join(" / ");
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.items.push(art);
    else groups.push({ title, items: [art] });
  }
  return groups;
}

function metaLine(meta: Record<string, string>) {
  const bits = [meta["公布日期"] && `公布 ${meta["公布日期"]}`,
    meta["施行日期"] && `施行 ${meta["施行日期"]}`]
    .filter(Boolean);
  return bits.join(" · ");
}
