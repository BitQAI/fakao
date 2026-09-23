"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import CaseDocument from "@/components/CaseDocument";
import { neighborPath, type ReaderContext } from "@/lib/caseNav";
import type {
  CaseNeighborItem, CaseNeighbors, CaseViewRecord,
} from "@/lib/caseLibTypes";

/** 案例阅读视图：吸顶导航（返回 / 上一篇 / 下一篇 / 进度）+ 进页打「看过」点。
 *
 *  导航条吸顶 → 不用滚回顶部就能切下一篇；←/→ 是同两个按钮的快捷键。
 */
export default function CaseReader({
  lib, loc, context, onBack, onOpen, onKeyword,
}: {
  lib: string;
  loc: string;
  context: ReaderContext;
  onBack: () => void;
  onOpen: (source: string, loc: string) => void;
  onKeyword: (keyword: string) => void;
}) {
  const [nav, setNav] = useState<CaseNeighbors | null>(null);
  const [seen, setSeen] = useState<CaseViewRecord | null>(null);
  // 同一篇只打一次点：dev 严格模式会二次挂载 effect，父组件重渲染也可能换 context 身份
  const marked = useRef<{ key: string; done: Promise<CaseViewRecord | null> } | null>(null);

  useEffect(() => {
    let alive = true;
    setNav(null);
    setSeen(null);
    // 先打点、再取前后篇：服务端据此把本篇当作「未看过」定位，
    // 并把「上一篇」算成阅读轨迹上刚看过的那一篇（见 spec §6.2）。
    (async () => {
      const key = `${lib}\u0000${loc}`;
      if (marked.current?.key !== key) {
        marked.current = { key, done: postJson<CaseViewRecord>(
          "/api/case/view", { source: lib, loc }).catch(() => null) };
      }
      const record = await marked.current.done;
      if (!alive) return;
      setSeen(record);
      const nav = await getJson<CaseNeighbors>(neighborPath(context, lib, loc))
        .catch(() => null);
      if (alive) setNav(nav);
    })();
    return () => { alive = false; };
  }, [lib, loc, context]);

  const jump = useCallback((item: CaseNeighborItem | null | undefined) => {
    if (item) onOpen(item.source, item.loc);
  }, [onOpen]);
  useArrowKeys(nav, jump);

  return (
    <>
      <div className="casereader-bar">
        <div className="casereader-row">
          <button className="casereader-btn" onClick={onBack}>← 返回</button>
          <button className="casereader-btn" disabled={!nav?.prev}
            title={nav?.prev?.title}
            onClick={() => jump(nav?.prev)}>上一篇</button>
          <button className="casereader-btn casereader-btn-primary" disabled={!nav?.next}
            title={nav?.next?.title}
            onClick={() => jump(nav?.next)}>下一篇</button>
        </div>
        <p className="casereader-status">
          {statusText(nav, seen, context.viewed === "")}
        </p>
      </div>
      <CaseDocument lib={lib} loc={loc} onKeyword={onKeyword} />
    </>
  );
}

/** ←/→ 切换上一篇/下一篇（输入框聚焦时不抢键）。 */
function useArrowKeys(
  nav: CaseNeighbors | null,
  jump: (item: CaseNeighborItem | null | undefined) => void,
) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      if (isTypingTarget(document.activeElement)) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); jump(nav?.prev); }
      else if (e.key === "ArrowRight") { e.preventDefault(); jump(nav?.next); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav, jump]);
}

function isTypingTarget(el: Element | null) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
    || (el as HTMLElement).isContentEditable;
}

function statusText(nav: CaseNeighbors | null, seen: CaseViewRecord | null,
                    showPosition: boolean) {
  const parts: string[] = [];
  // 位置只在「本次首次阅读 + 无阅读状态筛选」时展示：其余情况是打点后的临时排序位置
  if (showPosition && seen?.first_time && nav && nav.index >= 0) {
    parts.push(`第 ${nav.index + 1} / ${nav.total} 篇`);
  }
  if (seen) parts.push(seen.first_time ? "首次阅读" : `已看过 ${seen.views} 次`);
  if (nav && nav.prev && nav.next) parts.push("← / → 切换");
  return parts.join(" · ") || "…";
}
