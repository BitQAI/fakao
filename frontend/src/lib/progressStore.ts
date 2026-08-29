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
