"use client";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { getJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";

export interface SourceTarget {
  kind: "case" | "file";
  ref: string;
  loc: string;
}

function splitStatute(s: string): { law: string; no: string } {
  const m = s.match(/^(.+?)(?:第)?([0-9零一二三四五六七八九十百千]+)条(.*)$/);
  if (!m) return { law: s, no: "" };
  return { law: m[1], no: `${m[2]}条${m[3]}` };
}

/** 从条号里取阿拉伯数字，供法条页锚点定位；中文条号或缺失时返回 null。 */
function articleNumber(no: string): string | null {
  const m = no.match(/^(\d+)条/);
  return m ? m[1] : null;
}

interface SourceData {
  kind: "case" | "file";
  title: string;
  text: string;
  offset?: number | null;
  loc?: string;
}

export default function SourceViewer({
  source, statute, onClose,
}: {
  source: SourceTarget | null;
  statute?: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<SourceData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!source && !statute) return;
    setLoading(true);
    setError("");
    setData(null);
    const fetchUrl = statute ? (() => {
      const { law, no } = splitStatute(statute as string);
      return `/api/statute?law=${encodeURIComponent(law)}&no=${encodeURIComponent(no)}`;
    })() : `/api/source?ref=${encodeURIComponent(source!.ref)}&loc=${encodeURIComponent(source!.loc)}`;
    getJson<SourceData>(fetchUrl)
      .then((d) => setData(statute ? { ...d, title: statute } : d))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [source, statute]);

  if (!source && !statute) return null;
  if (!mounted) return null;
  return createPortal((
    <div className="source-modal" onClick={onClose}>
      <div className="source-panel" onClick={(e) => e.stopPropagation()}>
        <div className="ai-chat-head">
          <b>{data?.title ?? source?.ref ?? statute}</b>
          <button onClick={onClose}>×</button>
        </div>
        <div className="source-body">
          {statute && (() => {
            const { law, no } = splitStatute(statute as string);
            const num = articleNumber(no);
            const href = `/statutes?law=${encodeURIComponent(law)}`
              + (num ? `&no=${num}` : "");
            return (
              <a className="chip" href={href} style={{ marginBottom: 10 }}>
                在法条库中打开全文 →
              </a>
            );
          })()}
          {loading && <p className="muted">加载中…</p>}
          {error && <p className="bad">原文不可用：{error}</p>}
          {data && (
            <div
              className="source-text"
              dangerouslySetInnerHTML={{ __html: mdToHtml(data.text) }}
            />
          )}
        </div>
      </div>
    </div>
  ), document.body);
}
