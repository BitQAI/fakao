"use client";
import { useCallback, useEffect, useState } from "react";
import { delJson, getJson } from "@/lib/api";
import type { CaseHistoryResult } from "@/lib/caseLibTypes";

const LIMIT = 30;

/** 阅读历史（服务端 case_views）：可折叠面板，点条目直接进阅读视图。 */
export default function CaseHistoryPanel({
  onOpen,
}: {
  onOpen: (source: string, loc: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<CaseHistoryResult | null>(null);

  const load = useCallback(() => {
    getJson<CaseHistoryResult>(`/api/case/history?limit=${LIMIT}`)
      .then(setData)
      .catch(() => setData(null));
  }, []);

  // 折叠时也拉一次：按钮上要显示「最近看过（N）」
  useEffect(() => { load(); }, [load]);

  const clear = () => {
    if (!window.confirm("清空阅读历史？「已看」标记也会一起重置。")) return;
    delJson<{ cleared: number }>("/api/case/history").then(load).catch(() => {});
  };

  return (
    <div className="casehist">
      <button className={`casehist-toggle${open ? " active" : ""}`}
        onClick={() => setOpen(!open)}>
        <span>🕘 最近看过{data ? `（${data.total}）` : ""}</span>
        <span className="casehist-caret">{open ? "收起" : "展开"}</span>
      </button>

      {open && (
        <div className="casehist-panel">
          {!data || data.items.length === 0 ? (
            <p className="muted">
              还没有阅读记录：点开任意一篇案例，就会记进这里。
            </p>
          ) : data.items.map((item) => (
            <button key={`${item.source}-${item.loc}`} className="casehist-row"
              onClick={() => onOpen(item.source, item.loc)}>
              <span className="caselib-hit-title">{item.title}</span>
              <span className="muted">
                {[shortSource(item.source), item.date, when(item.last_viewed_at),
                  item.views > 1 ? `看过 ${item.views} 次` : ""]
                  .filter(Boolean).join(" · ")}
              </span>
            </button>
          ))}
          {data && data.items.length > 0 && (
            <div className="casehist-foot">
              {data.total > data.items.length
                && <span className="muted">仅显示最近 {data.items.length} 篇</span>}
              <button className="caselib-reset" onClick={clear}>清空历史</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function shortSource(source: string) {
  return source.replace("案例库", "").replace("指导性案例", "") || source;
}

/** 最近打开时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / MM-DD。 */
function when(ts: string) {
  const time = new Date(ts).getTime();
  if (!time) return "";
  const mins = Math.floor((Date.now() - time) / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days} 天前` : ts.slice(5, 10);
}
