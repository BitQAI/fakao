"use client";
import { useEffect, useRef, useState } from "react";
import { postJson } from "@/lib/api";
import type { StatuteCard } from "@/lib/types";

interface Props {
  card: StatuteCard;
  index: number;
  total: number;
  onNext: () => void;
}

/** 听学里的法条题卡：音频含「依据 + 条文 + 题干 + 答案 + 解析」。 */
export default function ListenCardView({ card, index, total, onNext }: Props) {
  const [showAnswer, setShowAnswer] = useState(false);
  const [error, setError] = useState("");
  const playedRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    setShowAnswer(false);
    setError("");
    playedRef.current = false;
  }, [card.quiz_id]);

  async function next() {
    if (playedRef.current) {
      try {
        await postJson("/api/cards/seen", { quiz_id: card.quiz_id, mode: "listen" });
      } catch {
        /* 进度写入失败不阻断听学 */
      }
    }
    onNext();
  }

  return (
    <div className="card" data-testid="listen-card">
      <p className="muted">
        听学法条题卡 {index + 1} / {total} · {card.subject}
        {card.unseen ? " · 新卡" : ""}
      </p>
      <span className="tag">依据：{card.basis}</span>
      <audio
        ref={audioRef}
        controls
        autoPlay
        key={card.quiz_id}
        src={`/api/audio/card/${card.quiz_id}`}
        onPlay={() => { playedRef.current = true; setError(""); }}
        onEnded={() => setShowAnswer(true)}
        onError={() => setError("音频生成中，稍后重试或点「下一张」")}
      />
      <h3>{card.stem}</h3>
      {card.options.length > 0 && (
        <div className="options-col">
          {card.options.map((opt) => (
            <span key={opt} className="option">{opt}</span>
          ))}
        </div>
      )}
      {error && <p className="muted">{error}</p>}
      <div className="row">
        <button className="btn btn-ghost" onClick={() => setShowAnswer((v) => !v)}>
          {showAnswer ? "收起答案" : "看答案"}
        </button>
        <button className="btn btn-primary" onClick={() => void next()}>下一张</button>
      </div>
      {showAnswer && (
        <div className="result ok">
          <b>答案：{card.answer}</b>
          {card.analysis && <div className="analysis">{card.analysis}</div>}
          {card.article_text && (
            <p className="note">条文：{card.article_text.slice(0, 200)}</p>
          )}
        </div>
      )}
    </div>
  );
}
