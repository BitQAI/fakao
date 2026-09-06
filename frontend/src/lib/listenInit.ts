import { getJson, postJson } from "@/lib/api";
import { readSavedQueue } from "@/lib/progressStore";
import { readListenCustom, clearListenCustom } from "@/lib/progressStore";
import type { Entry, ListenPayload } from "@/lib/types";

/** 听学分页：首屏取 10 条，剩 3 条时后台续取 10 条（见 ListenView 自动续取）。 */
export const LISTEN_PAGE = 10;
export const LISTEN_THRESHOLD = 3;

export async function loadListenInitial(entryParam: string | null): Promise<{
  queue: ListenPayload;
  idx: number;
  customRange: { subjects: string[]; points: string[] } | null;
  seenIds: string[];
  remaining: number;
  heardTotal: number;
  listenedToday: string[];
  deep: boolean;
}> {
  const targetReq = entryParam ? getJson<Entry>(`/api/entries/${encodeURIComponent(entryParam)}`).catch(() => null) : Promise.resolve(null);
  const custom = !entryParam ? readListenCustom() : null;
  if (custom && custom.range && (custom.range.subjects.length || custom.range.points.length)) {
    try {
      const r = await postJson<ListenPayload>("/api/listen/custom", {
        subjects: custom.range.subjects,
        points: custom.range.points,
        limit: custom.limit || LISTEN_PAGE,
        exclude: custom.exclude || [],
      });
      if (r.items.length) {
        const savedIdx = Math.min(custom.idx, Math.max(r.items.length - 1, 0));
        // 合并全局今日已听
        let listenedToday = r.items.filter((i) => i.listened_today).map((i) => i.id);
        try {
          const d = await getJson<{ items: { entry_id: string; ts: string }[] }>("/api/reviews/history?mode=listen&limit=500");
          const today = new Date().toISOString().slice(0, 10);
          const todayIds = Array.from(new Set(d.items.filter((it) => it.ts.startsWith(today)).map((it) => it.entry_id)));
          listenedToday = Array.from(new Set([...todayIds, ...listenedToday]));
        } catch {}
        let heardTotal = r.heard_total ?? 0;
        try {
          const q = await getJson<ListenPayload>(`/api/listen?limit=${LISTEN_PAGE}`);
          heardTotal = q.heard_total ?? heardTotal;
        } catch {}
        return {
          queue: r,
          idx: savedIdx,
          customRange: custom.range,
          seenIds: custom.seenIds || [],
          remaining: custom.remaining ?? Math.max(0, (r.remaining ?? 0) - r.items.length),
          heardTotal,
          listenedToday,
          deep: false,
        };
      }
      clearListenCustom();
    } catch {
      clearListenCustom();
    }
  }
  const [q, target] = await Promise.all([getJson<ListenPayload>(`/api/listen?limit=${LISTEN_PAGE}`), targetReq]);
  let items = q.items;
  let deep = false;
  if (target) {
    items = [target, ...q.items.filter((i) => i.id !== (target as Entry).id)];
    deep = true;
  }
  const saved = readSavedQueue("fakao.listen.queue.v1");
  let startIdx = 0;
  if (!entryParam && saved && saved.ids.length === items.length && saved.ids.every((id, i) => id === items[i].id)) {
    startIdx = Math.min(saved.idx, Math.max(items.length - 1, 0));
  }
  return {
    queue: { ...q, items },
    idx: startIdx,
    customRange: null,
    seenIds: [],
    remaining: 0,
    heardTotal: q.heard_total ?? 0,
    listenedToday: items.filter((i) => (i as any).listened_today).map((i) => i.id),
    deep,
  };
}
