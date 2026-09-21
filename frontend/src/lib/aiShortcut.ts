/** 「问 AI」快捷入口（看背/听学共用）：派发 ask-ai 打开聊天并回带当前条目，同时查历史条数。 */
import { useEffect, useRef, useState } from "react";
import { getJson } from "@/lib/api";
import type { Entry } from "@/lib/types";

export type AiShortcutEntry = Pick<Entry, "id" | "point" | "anchor" | "conclusion">;

// 同一条目问过 AI 则显示历史徽标：结果缓存，切回该条目不重复请求
const countCache = new Map<string, number>();

export function useAiShortcut(entry: AiShortcutEntry | null | undefined) {
  const entryId = entry?.id ?? "";
  const [aiCount, setAiCount] = useState<number | null>(null);
  const entryIdRef = useRef("");
  entryIdRef.current = entryId;

  useEffect(() => {
    if (!entryId) {
      setAiCount(null);
      return;
    }
    const cached = countCache.get(entryId);
    if (cached !== undefined) {
      setAiCount(cached);
      return;
    }
    setAiCount(null);
    let cancelled = false;
    getJson<{ items: unknown[] }>(
      `/api/assistant/history?entry_id=${encodeURIComponent(entryId)}&limit=50`
    ).then((d) => {
      if (cancelled) return;
      countCache.set(entryId, d.items.length);
      setAiCount(d.items.length);
    }).catch(() => {
      if (!cancelled) setAiCount(null);
    });
    return () => { cancelled = true; };
  }, [entryId]);

  // AI 回答完成后由 AiChat 广播 ai-asked，徽标即时 +1
  useEffect(() => {
    function handler(e: Event) {
      const askedId = (e as CustomEvent<{ entry_id?: string }>).detail?.entry_id;
      if (!askedId) return;
      const next = (countCache.get(askedId) ?? 0) + 1;
      countCache.set(askedId, next);
      if (entryIdRef.current === askedId) setAiCount(next);
    }
    window.addEventListener("ai-asked", handler);
    return () => window.removeEventListener("ai-asked", handler);
  }, []);

  function askAi() {
    if (!entry) return;
    window.dispatchEvent(new CustomEvent("ask-ai", {
      detail: {
        entry_id: entry.id,
        question: `讲解「${entry.point}」的要点和易错点`,
        title: entry.point,
        description: `场景：${entry.anchor}\n结论：${entry.conclusion}`,
      },
    }));
  }

  return { askAi, aiLabel: aiCount ? ` · ${aiCount}条历史` : "" };
}
