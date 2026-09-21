"use client";
import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from "react";

interface Options {
  setNotice: Dispatch<SetStateAction<string>>;
  /** 自增后重挂音频元素 → 重新发起请求（断点续播靠 resumeRef） */
  setPlayNonce: Dispatch<SetStateAction<number>>;
  maxRetry?: number;
}

/** 听学音频的容错：断线退避重连 + 缓冲卡死看门狗 + 断点续播位置。 */
export function useListenAudio({ setNotice, setPlayNonce, maxRetry = 3 }: Options) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const durRef = useRef(0);
  const playedRef = useRef(0);
  const exposedRef = useRef(false);
  const retryRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);
  const stallTimerRef = useRef<number | null>(null);
  const resumeRef = useRef(0);
  const recoveringRef = useRef(false);

  const clearStallTimer = useCallback(() => {
    if (stallTimerRef.current !== null) {
      window.clearTimeout(stallTimerRef.current);
      stallTimerRef.current = null;
    }
  }, []);

  const handleAudioError = useCallback(() => {
    clearStallTimer();
    const n = retryRef.current;
    // 404/503/断网在浏览器侧都表现为媒体错误，无法可靠区分：统一按瞬时故障退避重试
    if (n < maxRetry) {
      retryRef.current = n + 1;
      resumeRef.current = playedRef.current;
      recoveringRef.current = true;
      setNotice(`网络波动，正在重连（${n + 1}/${maxRetry}）…`);
      if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current);
      const delay = [1500, 3000, 6000][n] ?? 6000;
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = null;
        setPlayNonce((v) => v + 1); // remount 音频元素重建请求，加载后自动断点续播
      }, delay);
    } else {
      recoveringRef.current = false;
      setNotice("音频加载失败，已停止重连。请检查网络，或点「下一个」跳过。");
    }
  }, [clearStallTimer, maxRetry, setNotice, setPlayNonce]);

  // 长时间缓冲无进展视为卡死，走同样的重连路径（10 秒看门狗）
  const armStallTimer = useCallback(() => {
    clearStallTimer();
    stallTimerRef.current = window.setTimeout(() => {
      stallTimerRef.current = null;
      handleAudioError();
    }, 10000);
  }, [clearStallTimer, handleAudioError]);

  const handleAudioRecovered = useCallback(() => {
    clearStallTimer();
    retryRef.current = 0;
    if (recoveringRef.current) {
      recoveringRef.current = false;
      setNotice("");
    }
  }, [clearStallTimer, setNotice]);

  /** 切段时重置播放进度与重连状态（由视图在 idx 变化时调用）。 */
  const resetForSegment = useCallback(() => {
    durRef.current = 0;
    playedRef.current = 0;
    exposedRef.current = false;
    retryRef.current = 0;
    resumeRef.current = 0;
    recoveringRef.current = false;
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    clearStallTimer();
  }, [clearStallTimer]);

  // 卸载时清理重连定时器
  useEffect(() => () => {
    if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current);
    if (stallTimerRef.current !== null) window.clearTimeout(stallTimerRef.current);
  }, []);

  return {
    audioRef, durRef, playedRef, exposedRef, resumeRef,
    clearStallTimer, handleAudioError, armStallTimer, handleAudioRecovered,
    resetForSegment,
  };
}
