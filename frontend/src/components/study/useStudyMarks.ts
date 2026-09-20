"use client";
import { useEffect, useState } from "react";
import { delJson, getJson, postJson } from "@/lib/api";
import { readMarked, writeMarked } from "@/lib/progressStore";
import type { MarkItem } from "@/lib/types";

/** 标记（看背/听学共用）：服务端 /api/marks，挂载时把本地旧标记迁移上来。 */
export function useStudyMarks() {
  const [marked, setMarked] = useState<MarkItem[]>([]);
  const [error, setError] = useState("");

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
    }).catch(() => { /* 未登录/离线时忽略 */ });
  }, []);

  function markOf(entryId: string): MarkItem | undefined {
    return marked.find((m) => m.entry_id === entryId);
  }

  async function toggleMark(entryId: string) {
    const current = markOf(entryId);
    if (current) return removeMark(current);
    try {
      await postJson("/api/marks", { entry_id: entryId });
      const fresh = await getJson<{ items: MarkItem[] }>("/api/marks");
      setMarked(fresh.items);
    } catch (e) {
      setError("标记失败：" + String(e));
    }
  }

  async function removeMark(m: MarkItem) {
    try {
      await delJson(`/api/marks/${m.id}`);
      setMarked((p) => p.filter((x) => x.id !== m.id));
    } catch (e) {
      setError("取消失败：" + String(e));
    }
  }

  async function clearMarks() {
    try {
      await delJson("/api/marks");
      setMarked([]);
    } catch (e) {
      setError("清空失败：" + String(e));
    }
  }

  return { marked, error, setError, markOf, toggleMark, removeMark, clearMarks };
}
