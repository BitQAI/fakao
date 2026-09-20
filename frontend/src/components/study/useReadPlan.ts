"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getJson } from "@/lib/api";
import { readSavedQueue, writeSavedQueue } from "@/lib/progressStore";
import type { Entry, Plan } from "@/lib/types";

/** 看背队列位置记忆（刷新/离开后回来可恢复；条目与题卡在同一条队列里）。 */
export const READ_STORE_KEY = "fakao.read.queue.v1";

interface Hooks {
  /** 今日计划或深链加载完成（用于初始化「今日已看」集合） */
  onPlan: (plan: Plan) => void;
  /** ?queue=wrong：错题重练队列 */
  onWrongQueue: (items: Entry[]) => void;
}

/** 看背取数：今日计划 / 深链定位 / 错题重练，并持久化队列位置。 */
export function useReadPlan(hooks: Hooks) {
  const searchParams = useSearchParams();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");
  const hooksRef = useRef(hooks);
  hooksRef.current = hooks;

  function restoreQueue(p: Plan) {
    const saved = readSavedQueue(READ_STORE_KEY);
    let startIdx = 0;
    if (saved && saved.ids.length) {
      // 公共前缀：今日计划不变时精确恢复；「继续」追加的条目刷新后丢失时回退到计划末尾
      let common = 0;
      while (common < saved.ids.length && common < p.items.length &&
             saved.ids[common] === p.items[common].id) {
        common++;
      }
      if (common > 0) startIdx = Math.min(saved.idx, common);
    }
    setPlan(p);
    setIndex(startIdx);
  }

  useEffect(() => {
    const entryParam = searchParams.get("entry");
    const queueParam = searchParams.get("queue");
    if (queueParam === "wrong") {
      getJson<{ items: Entry[] }>("/api/wrongbook/queue?limit=30")
        .then((r) => {
          hooksRef.current.onWrongQueue(r.items);
          setIndex(0);
        })
        .catch((e) => setError(String(e)));
      return;
    }
    getJson<Plan>("/api/plans/today")
      .then((p) => {
        hooksRef.current.onPlan(p);
        if (!entryParam) {
          restoreQueue(p);
          return;
        }
        // 深链：目标条目置首，其余沿用今日计划（去重）
        getJson<Entry>(`/api/entries/${encodeURIComponent(entryParam)}`)
          .then((e) => {
            setPlan({
              date: p.date, quota: p.quota, rationale: p.rationale,
              items: [e, ...p.items.filter((i) => i.id !== e.id)],
              counts: p.counts,
            });
            setIndex(0);
          })
          .catch(() => restoreQueue(p));
      })
      .catch((e) => setError(String(e)));
  }, [searchParams]);

  useEffect(() => {
    if (!plan || plan.items.length === 0) return;
    writeSavedQueue(READ_STORE_KEY, plan.items.map((i) => i.id), index);
  }, [plan, index]);

  return { plan, setPlan, index, setIndex, error, setError };
}
