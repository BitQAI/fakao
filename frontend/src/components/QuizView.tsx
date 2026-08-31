"use client";
import { useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import GroupQuizView from "./GroupQuizView";
import type { QuizHistoryItem, QuizQuestion } from "@/lib/types";

interface AnswerResult { correct: boolean; answer: string; analysis?: string; }

export default function QuizView() {
  const [view, setView] = useState<"today" | "group" | "history">("today");
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [history, setHistory] = useState<QuizHistoryItem[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<string[]>([]);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [start, setStart] = useState(Date.now());
  const [error, setError] = useState("");

  useEffect(() => {
    getJson<{ questions: QuizQuestion[] }>("/api/quiz/today")
      .then((d) => { setQuestions(d.questions); setStart(Date.now()); })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (view === "history" && history === null) {
      getJson<{ items: QuizHistoryItem[] }>("/api/quiz/history")
        .then((d) => setHistory(d.items))
        .catch((e) => setError(String(e)));
    }
  }, [view, history]);

  if (error) return <p className="muted">加载失败：{error}</p>;

  if (view === "group") {
    return (
      <div>
        <QuizSegments view={view} setView={setView} />
        <GroupQuizView />
      </div>
    );
  }

  if (view === "history") {
    return (
      <div>
        <QuizSegments view={view} setView={setView} />
        {!history ? <p className="muted">加载中…</p> : history.length === 0 ? (
          <div className="card"><p className="muted">还没有做题记录，先去「今日」自测几题吧。</p></div>
        ) : (
          <div className="history-list">
            {history.map((item) => (
              <div className="card history-card" key={item.answer_id}>
                <div className="history-head">
                  <span className={`badge${item.correct ? "" : " badge-red"}`}>
                    {item.correct ? "答对" : "答错"}
                  </span>
                  <span className="muted">{item.ts.slice(0, 16).replace("T", " ")}</span>
                </div>
                <p className="history-stem">{item.stem}</p>
                {item.qtype === "choice" ? (
                  <div className="options-col">
                    {item.options.map((opt, i) => {
                      const letter = String.fromCharCode(65 + i);
                      const picked = item.user_answer.includes(letter);
                      const isCorrect = item.answer.toUpperCase().includes(letter);
                      let cls = "option history-option";
                      if (isCorrect) cls += " correct";
                      else if (picked) cls += " wrong";
                      return (
                        <div key={opt} className={cls}>
                          {isCorrect && picked && (
                            <span className="option-mark ok">✓</span>
                          )}
                          {picked && !isCorrect && (
                            <span className="option-mark bad">✗</span>
                          )}
                          {opt}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="muted">自评：{item.correct ? "答对了" : "答错了"} · 正确答案：{item.answer}</p>
                )}
                {item.qtype === "choice" && (
                  <p className="muted">正确答案：{item.answer}</p>
                )}
                <div className="analysis" dangerouslySetInnerHTML={{ __html: mdToHtml(item.analysis) }} />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

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
  const isMulti = q.qtype === "choice" && q.answer.trim().length > 1;

  async function submit(answer: string, correctOverride?: boolean) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const duration = Math.round((Date.now() - start) / 1000);
      const r = await postJson<AnswerResult>("/api/quiz/answer", {
        quiz_id: q.id, user_answer: answer, correct: correctOverride, duration_sec: duration,
      });
      setResult(r);
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    setPicked([]); setResult(null); setShowAnswer(false); setStart(Date.now());
    setIdx((i) => i + 1);
  }

  function toggle(letter: string) {
    if (result) return;
    if (isMulti) {
      setPicked((p) => (p.includes(letter) ? p.filter((x) => x !== letter) : [...p, letter]));
    } else {
      setPicked([letter]);
      void submit(letter);
    }
  }

  return (
    <div>
      <QuizSegments view={view} setView={setView} />
      <p className="muted">{idx + 1} / {questions.length}</p>
      <div className="card">
        <h3>{q.stem}</h3>
        {q.qtype === "choice" ? (
          <>
            {isMulti && <span className="badge">多选题</span>}
            <div className="options-col">
              {q.options.map((opt, i) => {
                const letter = String.fromCharCode(65 + i);
                const isPicked = picked.includes(letter);
                let cls = `option${isPicked ? " picked" : ""}`;
                if (result) {
                  const isCorrect = result.answer.toUpperCase().includes(letter);
                  const isWrongPick = isPicked && !isCorrect;
                  if (isCorrect) cls += " correct";
                  else if (isWrongPick) cls += " wrong";
                }
                return (
                  <button
                    key={opt}
                    className={cls}
                    disabled={result !== null || submitting}
                    onClick={() => toggle(letter)}
                  >
                    {isMulti && (
                      <span className={`option-check${isPicked ? " checked" : ""}`}>
                        {isPicked ? "✓" : ""}
                      </span>
                    )}
                    {opt}
                  </button>
                );
              })}
            </div>
            {isMulti && !result && (
              <div className="row">
                <button className="btn btn-primary" disabled={picked.length === 0 || submitting}
                  onClick={() => void submit(picked.join(""))}>
                  提交答案
                </button>
              </div>
            )}
          </>
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
            {q.qtype === "choice" && isMulti && (
              <p className="muted">正确答案：{result.answer}</p>
            )}
            {q.qtype === "cloze" && <p className="muted">正确答案：{result.answer}</p>}
            <div className="analysis" dangerouslySetInnerHTML={{ __html: mdToHtml(result.analysis || `正确答案：${result.answer}`) }} />
            <button className="btn btn-ghost" onClick={next}>下一题</button>
          </div>
        )}
      </div>
    </div>
  );
}

function QuizSegments({
  view, setView,
}: {
  view: "today" | "group" | "history";
  setView: (v: "today" | "group" | "history") => void;
}) {
  return (
    <div className="segments quiz-segments">
      <button className={`segment${view === "today" ? " active" : ""}`}
        onClick={() => setView("today")}>今日</button>
      <button className={`segment${view === "group" ? " active" : ""}`}
        onClick={() => setView("group")}>组卷</button>
      <button className={`segment${view === "history" ? " active" : ""}`}
        onClick={() => setView("history")}>历史</button>
    </div>
  );
}
