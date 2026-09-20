"use client";
import type { ReactNode } from "react";

export type RateResult = "good" | "fuzzy" | "bad";

interface Props {
  /** 卡面顶部标签：条目卡是「科目 · 子模块」，题卡是「科目 · 法条库主名」 */
  tag: ReactNode;
  /** 卡面标题（条目是考点，题卡是题干） */
  title: ReactNode;
  /** 标题后的徽章行（已标记 / 今日已看 / 已看 N 次 / 未看） */
  badges?: ReactNode;
  /** 正面正文（条目是场景，题卡是选项） */
  frontBody?: ReactNode;
  frontHint: string;
  /** 背面全部内容 */
  back: ReactNode;
  flipped: boolean;
  onFlip: () => void;
  onRate?: (result: RateResult) => void;
  submitting?: boolean;
}

/** 看背卡片外壳：条目卡与法条题卡共用同一套翻面 / 徽章 / 三档自评结构。 */
export default function StudyCardShell({
  tag, title, badges, frontBody, frontHint, back, flipped, onFlip, onRate, submitting,
}: Props) {
  return (
    <div>
      <div className={`flashcard${flipped ? " flipped" : ""}`} onClick={onFlip}>
        <div className="flashcard-inner">
          <div className="flashcard-face">
            <span className="tag">{tag}</span>
            <h2>{title}{badges}</h2>
            {frontBody}
            <p className="hint">{frontHint}</p>
          </div>
          <div className="flashcard-face back">{back}</div>
        </div>
      </div>
      {flipped && onRate && (
        <div className="rate-row">
          <button className="btn btn-bad" disabled={submitting}
            onClick={() => onRate("bad")}>没记住</button>
          <button className="btn btn-ghost" disabled={submitting}
            onClick={() => onRate("fuzzy")}>模糊</button>
          <button className="btn btn-good" disabled={submitting}
            onClick={() => onRate("good")}>{submitting ? "保存中…" : "记住了"}</button>
        </div>
      )}
    </div>
  );
}
