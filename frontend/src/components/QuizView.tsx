"use client";
import { useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import type { QuizQuestion } from "@/lib/types";

interface AnswerResult { correct: boolean; answer: string; }

export default function QuizView() {
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);
  const [start, setStart] = useState(Date.now());
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<{ questions: QuizQuestion[] }>("/api/quiz/today")
      .then((d) => { setQuestions(d.questions); setStart(Date.now()); })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="muted">加载失败：{error}</p>;
  if (!questions) return <p className="muted">生成题目中…</p>;
  if (questions.length === 0) return <div className="card"><p>今天没有自测题。</p></div>;
  if (idx >= questions.length) {
    return (
      <div className="card center">
        <h2>今日自测完成</h2>
        <p className="muted">共 {questions.length} 题，去「报告」看复盘。</p>
      </div>
    );
  }

  const q = questions[idx];

  async function submit(answer: string, correctOverride?: boolean) {
    const duration = Math.round((Date.now() - start) / 1000);
    const r = await postJson<AnswerResult>("/api/quiz/answer", {
      quiz_id: q.id, user_answer: answer, correct: correctOverride, duration_sec: duration,
    });
    setResult(r);
  }

  function next() {
    setPicked(""); setResult(null); setShowAnswer(false); setStart(Date.now());
    setIdx((i) => i + 1);
  }

  return (
    <div>
      <p className="muted">{idx + 1} / {questions.length}</p>
      <div className="card">
        <h3>{q.stem}</h3>
        {q.qtype === "choice" ? (
          <div className="options-col">
            {q.options.map((opt, i) => {
              const letter = String.fromCharCode(65 + i);
              const isPicked = picked === letter;
              const isCorrect = result !== null && result.answer === letter;
              const isWrongPick = result !== null && isPicked && !isCorrect;
              return (
                <button
                  key={opt}
                  className={`option${isPicked ? " picked" : ""}${isCorrect ? " correct" : ""}${isWrongPick ? " wrong" : ""}`}
                  disabled={result !== null}
                  onClick={() => { setPicked(letter); void submit(letter); }}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="options-col">
            <p className="muted">在脑子里补全结论，再看答案自评。</p>
            {!showAnswer ? (
              <button className="btn btn-primary" onClick={() => setShowAnswer(true)}>显示答案</button>
            ) : (
              <div className="row">
                <button className="btn btn-good" onClick={() => void submit("self", true)}>答对了</button>
                <button className="btn btn-bad" onClick={() => void submit("self", false)}>答错了</button>
              </div>
            )}
          </div>
        )}
        {result && (
          <div className={`result ${result.correct ? "ok" : "bad"}`}>
            <b>{result.correct ? "答对了" : "答错了"}</b>
            {q.qtype === "cloze" && <p className="muted">正确答案：{result.answer}</p>}
            <button className="btn btn-ghost" onClick={next}>下一题</button>
          </div>
        )}
      </div>
    </div>
  );
}
