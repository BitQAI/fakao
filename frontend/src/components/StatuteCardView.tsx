"use client";
import { useEffect, useState } from "react";
import { postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import type { StatuteCard } from "@/lib/types";

interface AnswerResult {
  correct: boolean;
  answer: string;
  analysis?: string;
}

interface Props {
  card: StatuteCard;
  index: number;
  total: number;
  mode?: "read" | "listen";
  onNext: () => void;
}

/** 看背/听学里的法条题卡：可先作答再看答案与条文原文。 */
export default function StatuteCardView({
  card, index, total, mode = "read", onNext,
}: Props) {
  const [picked, setPicked] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPicked("");
    setResult(null);
    setError("");
  }, [card.quiz_id]);

  async function answer(choice: string) {
    if (result || submitting) return;
    setPicked(choice);
    setSubmitting(true);
    try {
      const r = await postJson<AnswerResult>("/api/quiz/answer", {
        quiz_id: card.quiz_id, user_answer: choice, correct: false,
        duration_sec: 0,
      });
      setResult(r);
    } catch (e) {
      setError("作答未记录：" + String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function next() {
    try {
      await postJson("/api/cards/seen", { quiz_id: card.quiz_id, mode });
    } catch {
      /* 进度写入失败不阻断学习 */
    }
    onNext();
  }

  const isChoice = card.qtype === "choice";
  return (
    <div className="card" data-testid="statute-card">
      <p className="muted">
        法条题卡 {index + 1} / {total} · {card.subject}
        {card.unseen ? " · 新卡" : ""}
      </p>
      <span className="tag">依据：{card.basis}</span>
      <h3>{card.stem}</h3>
      {isChoice ? (
        <div className="options-col">
          {card.options.map((opt, i) => {
            const letter = String.fromCharCode(65 + i);
            let cls = `option${picked === letter ? " picked" : ""}`;
            if (result) {
              const isCorrect = result.answer.toUpperCase().includes(letter);
              if (isCorrect) cls += " correct";
              else if (picked === letter) cls += " wrong";
            }
            return (
              <button key={opt} className={cls} disabled={result !== null || submitting}
                onClick={() => void answer(letter)}>
                {opt}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="row">
          <button className="btn btn-good" disabled={result !== null || submitting}
            onClick={() => void answer("对")}>对</button>
          <button className="btn btn-bad" disabled={result !== null || submitting}
            onClick={() => void answer("错")}>错</button>
        </div>
      )}
      {error && <p className="muted">{error}</p>}
      {!result ? (
        <div className="row">
          <button className="btn btn-ghost" onClick={() => void next()}>
            跳过，看答案
          </button>
        </div>
      ) : (
        <div className={`result ${result.correct ? "ok" : "bad"}`}>
          <b>{result.correct ? "答对了" : "答错了"}</b>
          <p className="muted">正确答案：{result.answer}</p>
          <div className="analysis"
            dangerouslySetInnerHTML={{
              __html: mdToHtml(result.analysis || card.analysis || ""),
            }} />
          {card.article_text && (
            <p className="note">条文：{card.article_text.slice(0, 160)}</p>
          )}
          <div className="row">
            <button className="btn btn-primary" onClick={() => void next()}>下一张</button>
          </div>
        </div>
      )}
      {!result && card.analysis && (
        <p className="hint">先选一个答案（或跳过）再看解析与条文</p>
      )}
    </div>
  );
}
