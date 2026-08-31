/** 学习队列位置记忆（localStorage）：听学/看背共用。 */

export interface SavedQueue {
  ids: string[];
  idx: number;
}

export function readSavedQueue(key: string): SavedQueue | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (Array.isArray(data.ids) && typeof data.idx === "number") return data;
  } catch { /* 忽略损坏的本地缓存 */ }
  return null;
}

export function writeSavedQueue(key: string, ids: string[], idx: number) {
  try {
    localStorage.setItem(key, JSON.stringify({ ids, idx }));
  } catch { /* 忽略存储失败 */ }
}

/** 听学标记条目（localStorage）：收藏想重背的条目，个人设备级，不上传。 */

export interface MarkedItem {
  id: string;
  subject: string;
  point: string;
  ts: number;
}

const LISTEN_MARK_KEY = "fakao.listen.marked.v1";

export function readMarked(): MarkedItem[] {
  try {
    const raw = localStorage.getItem(LISTEN_MARK_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    if (Array.isArray(data)) {
      return data.filter(
        (m) => m && typeof m.id === "string" && typeof m.point === "string"
      );
    }
  } catch { /* 忽略损坏的本地缓存 */ }
  return [];
}

export function writeMarked(items: MarkedItem[]) {
  try {
    localStorage.setItem(LISTEN_MARK_KEY, JSON.stringify(items));
  } catch { /* 忽略存储失败 */ }
}

export function toggleMarkedItem(
  items: MarkedItem[],
  e: { id: string; subject: string; point: string }
): MarkedItem[] {
  return items.some((m) => m.id === e.id)
    ? items.filter((m) => m.id !== e.id)
    : [...items, { id: e.id, subject: e.subject, point: e.point, ts: Date.now() }];
}
