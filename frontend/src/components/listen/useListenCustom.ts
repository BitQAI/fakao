"use client";
import { useState, type Dispatch, type SetStateAction } from "react";
import { getJson, postJson } from "@/lib/api";
import {
  clearListenCustom, clearListenCustomQueue, writeListenCustom, writeListenCustomQueue,
} from "@/lib/progressStore";
import type { ListenPayload } from "@/lib/types";
import type { CustomRange } from "../CustomRangePicker";
import { LISTEN_PAGE } from "@/lib/listenInit";

interface Options {
  queue: ListenPayload | null;
  setQueue: Dispatch<SetStateAction<ListenPayload | null>>;
  heardTotal: number;
  setHeardTotal: Dispatch<SetStateAction<number>>;
  setIdx: Dispatch<SetStateAction<number>>;
  setPlaying: Dispatch<SetStateAction<boolean>>;
  setDeep: Dispatch<SetStateAction<boolean>>;
  setNotice: Dispatch<SetStateAction<string>>;
  setListenedToday: Dispatch<SetStateAction<Set<string>>>;
}

/** 听学的自定义范围与续批：状态 + 取数（看背用同一套 CustomRange，含 kinds/laws）。 */
export function useListenCustom(opts: Options) {
  const {
    queue, setQueue, heardTotal, setHeardTotal, setIdx, setPlaying,
    setDeep, setNotice, setListenedToday,
  } = opts;
  const [customRange, setCustomRange] = useState<CustomRange | null>(null);
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set());
  const [remaining, setRemaining] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreCount, setMoreCount] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);

  async function applyCustom(range: CustomRange, o?: { exclude?: string[]; limit?: number }) {
    setLoadingMore(true);
    setNotice("");
    try {
      const exclude = o?.exclude ?? [];
      const limit = o?.limit ?? LISTEN_PAGE;
      const r = await postJson<ListenPayload>("/api/listen/custom", {
        subjects: range.subjects, points: range.points,
        kinds: range.kinds ?? [], laws: range.laws ?? [], limit, exclude,
      });
      if (!r.items.length) {
        if (exclude.length) setRemaining(0);
        setNotice(exclude.length ? "剩余已全部听完。" : "所选范围暂无听学内容（可能尚未合成音频）。");
        setPickerOpen(false);
        return;
      }
      setQueue(r);
      setHeardTotal(r.heard_total ?? heardTotal);
      const newSeen = new Set([...exclude, ...r.items.map((i) => i.id)]);
      setSeenIds(newSeen);
      const newRemaining = Math.max(0, (r.remaining ?? 0) - r.items.length);
      setRemaining(newRemaining);
      writeListenCustom({
        range, seenIds: Array.from(newSeen), remaining: newRemaining,
        idx: 0, limit, exclude, ts: Date.now(),
      });
      writeListenCustomQueue(r);
      getJson<{ items: { entry_id: string; ts: string }[] }>(
        "/api/reviews/history?mode=listen&limit=500")
        .then((d) => {
          const today = new Date().toISOString().slice(0, 10);
          const todayIds = Array.from(new Set(
            d.items.filter((it) => it.ts.startsWith(today)).map((it) => it.entry_id)));
          const newIds = r.items.filter((i) => i.listened_today).map((i) => i.id);
          setListenedToday(new Set([...todayIds, ...newIds]));
        })
        .catch(() => setListenedToday(
          new Set(r.items.filter((i) => i.listened_today).map((i) => i.id))));
      setCustomRange(range);
      setDeep(false);
      setIdx(0);
      setPlaying(false);
      setPickerOpen(false);
    } catch (e) {
      setNotice("加载失败：" + String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  async function loadMore(count: number) {
    if (count < 1 || count > 50) return;
    setLoadingMore(true);
    setNotice("");
    try {
      const items = queue?.items ?? [];
      const r = await postJson<ListenPayload>("/api/listen/more", {
        count, exclude: items.map((i) => i.id),
      });
      if (!r.items.length) {
        setNotice("没有更多听学内容了。");
        return;
      }
      setQueue((q) => (q ? { ...q, items: [...q.items, ...r.items], remaining: r.remaining } : q));
      setListenedToday((prev) => {
        const next = new Set(prev);
        r.items.forEach((it) => { if (it.listened_today) next.add(it.id); });
        return next;
      });
      setIdx(items.length);
      setPlaying(false);
    } catch (e) {
      setNotice("加载失败：" + String(e));
    } finally {
      setLoadingMore(false);
      setMoreCount("");
    }
  }

  function resetRange() {
    clearListenCustom();
    clearListenCustomQueue();
  }

  return {
    customRange, setCustomRange, seenIds, setSeenIds, remaining, setRemaining,
    loadingMore, setLoadingMore, moreCount, setMoreCount, pickerOpen, setPickerOpen,
    applyCustom, loadMore, resetRange,
  };
}
