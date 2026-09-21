"use client";
import { useEffect, useState } from "react";
import { delJson, getJson, postJson } from "@/lib/api";
import { readMarked, writeMarked } from "@/lib/progressStore";
import type { MarkItem } from "@/lib/types";

interface Options {
  onError?: (message: string) => void;
}

/** 听学标记（与看背共用 /api/marks）：挂载时把本地旧标记迁移上来。 */
export function useListenMarked({ onError }: Options = {}) {
  const [marked, setMarked] = useState<MarkItem[]>([]);
  const [marksOpen, setMarksOpen] = useState(false);

  useEffect(() => {
    getJson<{ items: MarkItem[] }>("/api/marks").then(async (d) => {
      setMarked(d.items);
      const legacy = readMarked();
      const existing = new Set(d.items.map((m) => m.entry_id));
      const pending = legacy.filter((m) => !existing.has(m.id));
      if (pending.length) {
        for (const m of pending) {
          try { await postJson("/api/marks", { entry_id: m.id }); } catch { /* 单条失败不阻断 */ }
        }
        writeMarked([]);
        const fresh = await getJson<{ items: MarkItem[] }>("/api/marks");
        setMarked(fresh.items);
      }
    }).catch(() => { /* 离线时忽略 */ });
  }, []);

  function isMarked(entryId: string): boolean {
    return marked.some((m) => m.entry_id === entryId);
  }

  async function toggleMark(entryId: string) {
    const current = marked.find((m) => m.entry_id === entryId);
    if (current) return removeMark(current);
    try {
      await postJson("/api/marks", { entry_id: entryId });
      const fresh = await getJson<{ items: MarkItem[] }>("/api/marks");
      setMarked(fresh.items);
    } catch (e) {
      onError?.("标记失败：" + String(e));
    }
  }

  async function removeMark(m: MarkItem) {
    try {
      await delJson(`/api/marks/${m.id}`);
      setMarked((p) => p.filter((x) => x.id !== m.id));
    } catch (e) {
      onError?.("取消失败：" + String(e));
    }
  }

  async function clearMarks() {
    try {
      await delJson("/api/marks");
      setMarked([]);
    } catch (e) {
      onError?.("清空失败：" + String(e));
    }
  }

  return { marked, marksOpen, setMarksOpen, isMarked, toggleMark, removeMark, clearMarks };
}
