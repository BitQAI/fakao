"use client";
import type { RefObject, SyntheticEvent } from "react";
import type { CaseRef, Entry } from "@/lib/types";

export interface AudioBinding {
  ref: RefObject<HTMLAudioElement>;
  src: string;
  audioKey: string;
  onLoadedMetadata: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onTimeUpdate: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onPlay: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onCanPlay: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onWaiting: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onStalled: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onPause: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onEnded: (e: SyntheticEvent<HTMLAudioElement>) => void;
  onError: (e: SyntheticEvent<HTMLAudioElement>) => void;
}

interface Props {
  entry: Entry;
  idx: number;
  total: number;
  heardTotal: number;
  remaining: number;
  generating: boolean;
  prefetching: boolean;
  playing: boolean;
  todayCount: number;
  listenedToday: boolean;
  isMarked: boolean;
  showText: boolean;
  aiLabel: string;
  audio: AudioBinding;
  onToggleText: () => void;
  onPrev: () => void;
  onNext: () => void;
  onToggleMark: () => void;
  onAskAi: () => void;
  onStatute: (statute: string) => void;
  onCase: (c: CaseRef) => void;
}

/** 听学的一段：正式条目与法条题卡共用（音频 / 徽章 / 进度行 / 按钮 / 原文）。 */
export default function ListenSegment({
  entry, idx, total, heardTotal, remaining, generating, prefetching, playing,
  todayCount, listenedToday, isMarked, showText, aiLabel, audio,
  onToggleText, onPrev, onNext, onToggleMark, onAskAi, onStatute, onCase,
}: Props) {
  const isCard = entry.kind === "card";
  return (
    <div className="card center" data-testid={isCard ? "listen-card" : "listen-segment"}>
      <h2>
        {entry.subject} · {entry.point}
        {isMarked && <span className="badge">已标记</span>}
        {(entry.listened_today || listenedToday) && <span className="badge">今日已听</span>}
        {entry.listen_count
          ? <span className="badge">已听 {entry.listen_count} 次</span>
          : <span className="badge">未听</span>}
      </h2>
      <p className="muted">
        第 {idx + 1} 段 / 队列 {total} · {entry.listen_count ? `本条已听 ${entry.listen_count} 次` : "本条未听"}
        {" "}· 今日累计 {todayCount} 条 · 累计已听 {heardTotal} · 剩余可听 {remaining}
        {generating ? " · 正在续批生成…" : ""}{prefetching ? " · 后面内容加载中…" : ""}
      </p>
      <p className="muted" style={{ fontSize: 12 }}>听学只记暴露，不记掌握</p>
      <audio
        ref={audio.ref} controls autoPlay key={audio.audioKey} src={audio.src}
        onLoadedMetadata={audio.onLoadedMetadata} onTimeUpdate={audio.onTimeUpdate}
        onPlay={audio.onPlay} onCanPlay={audio.onCanPlay}
        onWaiting={audio.onWaiting} onStalled={audio.onStalled}
        onPause={audio.onPause} onEnded={audio.onEnded} onError={audio.onError}
      />
      <div className="row">
        <button className="btn btn-ghost" disabled={idx === 0} onClick={onPrev}>上一个</button>
        <button className="btn btn-ghost" onClick={onToggleMark}>
          {isMarked ? "已标记 ✓" : "标记"}
        </button>
        <button className="btn btn-ghost" onClick={onNext}>{playing ? "跳过" : "下一段"}</button>
      </div>
      <div className="row">
        <button className="btn btn-ghost" onClick={onToggleText}>
          {showText ? "收起原文" : "显示原文"}
        </button>
        <button className="btn btn-ghost" onClick={onAskAi}>问 AI{aiLabel}</button>
      </div>
      {showText && (
        <div className="analysis" style={{ textAlign: "left" }}>
          {isCard ? (
            <>
              <p><b>依据：</b>{entry.statutes[0] ?? entry.submodule}</p>
              <p><b>题干：</b>{entry.anchor}</p>
              {(entry.options ?? []).length > 0 && (
                <p><b>选项：</b>{(entry.options ?? []).join("　")}</p>
              )}
              <p><b>答案：</b>{entry.conclusion}</p>
              {entry.rationale && <p><b>解析：</b>{entry.rationale}</p>}
              {entry.article_text && <p className="note">条文：{entry.article_text}</p>}
            </>
          ) : (
            <>
              <p><b>场景：</b>{entry.anchor}</p>
              <p><b>结论：</b>{entry.conclusion}</p>
              {entry.note && <p className="note">⚠ {entry.note}</p>}
              {entry.tts_text && <p className="muted">播报文本：{entry.tts_text}</p>}
            </>
          )}
          {entry.statutes.length > 0 && (
            <div className="source-chips" style={{ marginTop: 8 }}>
              {entry.statutes.map((st, i) => (
                <button key={i} className="chip" onClick={() => onStatute(st)}>{st}</button>
              ))}
            </div>
          )}
        </div>
      )}
      {entry.cases.length > 0 && (
        <div className="source-chips" style={{ justifyContent: "center" }}>
          {entry.cases.map((c, i) => (
            <button key={i} className="chip" onClick={() => onCase(c)}>
              查看原文 · 案例 {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
