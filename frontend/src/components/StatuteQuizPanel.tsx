"use client";
import { useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import type { StatuteCard } from "@/lib/types";

interface AnswerResult { correct: boolean; answer: string; analysis?: string; }

/** 法条页挂题：本条下的法条驱动题，点选项即作答并回显解析。 */
export default function StatuteQuizPanel({ lawKey, no, sub = 0 }: {
  lawKey: string; no: number; sub?: number;
}) {
  const [cards, setCards] = useState<StatuteCard[] | null>(null);
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [picked, setPicked] = useState<{ [qid: number]: string }>({});
  const [results, setResults] = useState<{ [qid: number]: AnswerResult }>({});
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setCards(null);
    getJson<{ items: StatuteCard[] }>(
      `/api/statute/questions?law=${encodeURIComponent(lawKey)}&no=${no}&sub=${sub}`)
      .then((d) => { if (alive) setCards(d.items); })
      .catch((e) => { if (alive) { setCards([]); setError(String(e)); } });
    return () => { alive = false; };
  }, [lawKey, no, sub]);

  async function answer(card: StatuteCard, choice: string) {
    if (results[card.quiz_id]) return;
    setPicked((p) => ({ ...p, [card.quiz_id]: choice }));
    try {
      const r = await postJson<AnswerResult>("/api/quiz/answer", {
        quiz_id: card.quiz_id, user_answer: choice, correct: false, duration_sec: 0,
      });
      setResults((s) => ({ ...s, [card.quiz_id]: r }));
      void postJson("/api/cards/seen", { quiz_id: card.quiz_id, mode: "quiz" })
        .catch(() => undefined);
    } catch (e) {
      setError("作答未记录：" + String(e));
    }
  }

  if (cards === null) return <p className="muted">题目加载中…</p>;
  if (cards.length === 0) {
    return <p className="muted">该条暂无题目{error ? `（${error}）` : ""}</p>;
  }
  return (
    <div className="statute-quiz">
      <p className="muted">练这一条（{cards.length} 题）</p>
      {cards.map((card, i) => {
        const result = results[card.quiz_id];
        const open = openIdx === i;
        return (
          <div key={card.quiz_id} className="quiz-mini">
            <button className="quiz-mini-head" onClick={() => setOpenIdx(open ? null : i)}>
              {open ? "▾" : "▸"} {card.stem}
            </button>
            {open && (
              <div className="quiz-mini-body">
                {card.qtype === "choice" ? (
                  <div className="options-col">
                    {card.options.map((opt, k) => {
                      const letter = String.fromCharCode(65 + k);
                      let cls = "option";
                      if (picked[card.quiz_id] === letter) cls += " picked";
                      if (result) {
                        if (result.answer.toUpperCase().includes(letter)) cls += " correct";
                        else if (picked[card.quiz_id] === letter) cls += " wrong";
                      }
                      return (
                        <button key={opt} className={cls} disabled={!!result}
                          onClick={() => void answer(card, letter)}>{opt}</button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="row">
                    {["对", "错"].map((v) => (
                      <button key={v} className="btn" disabled={!!result}
                        onClick={() => void answer(card, v)}>{v}</button>
                    ))}
                  </div>
                )}
                {result && (
                  <div className={`result ${result.correct ? "ok" : "bad"}`}>
                    <b>{result.correct ? "答对了" : "答错了"} · 正确答案 {result.answer}</b>
                    <div className="analysis" dangerouslySetInnerHTML={{
                      __html: mdToHtml(result.analysis || card.analysis || ""),
                    }} />
                    {card.article_text && (
                      <p className="note">条文：{card.article_text.slice(0, 200)}</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
