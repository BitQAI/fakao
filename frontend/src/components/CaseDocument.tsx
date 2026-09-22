"use client";
import { useEffect, useState } from "react";
import { getJson } from "@/lib/api";
import type { CaseDetail } from "@/lib/caseLibTypes";

/** 案例文书阅读：标题区 + 分节正文（裁判要旨/基本案情/裁判理由…）。 */
export default function CaseDocument({
  lib, loc, onKeyword,
}: {
  lib: string;
  loc: string;
  onKeyword: (keyword: string) => void;
}) {
  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setError("");
    const sp = new URLSearchParams({ source: lib, loc });
    getJson<CaseDetail>(`/api/case/detail?${sp}`)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [lib, loc]);

  if (error) {
    return <p className="bad">
      {error.includes("404") ? "案例库中没有这篇案例。" : `加载失败：${error}`}
    </p>;
  }
  if (!data) return <p className="muted">加载中…</p>;

  return (
    <article className="caselib-doc">
      <h3 className="caselib-title">{data.title}</h3>
      <p className="caselib-meta">
        {[data.source, data.category, data.case_no, data.date].filter(Boolean).join(" · ")}
      </p>
      {data.keywords.length > 0 && (
        <div className="caselib-tags">
          {data.keywords.map((kw) => (
            <button key={kw} className="caselib-tag" onClick={() => onKeyword(kw)}>
              {kw}
            </button>
          ))}
        </div>
      )}
      {data.sections.map((section, i) => (
        <section key={`${section.label}-${i}`} className="caselib-section">
          {section.label && <h4 className="caselib-section-head">{section.label}</h4>}
          {section.text.split("\n").map((para, j) => (
            <p key={j} className="caselib-para">{para}</p>
          ))}
        </section>
      ))}
      <p className="hint">
        {data.paragraphs_dropped > 0
          && `已自动合并重复段落 ${data.paragraphs_dropped} 处 ｜ `}
        {data.url
          ? <a className="caselib-link" href={data.url} target="_blank"
              rel="noreferrer">查看来源原文</a>
          : "案例来源：法考案例库统一索引"}
      </p>
    </article>
  );
}
