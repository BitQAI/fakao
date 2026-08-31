"use client";
import { useEffect, useRef, useState } from "react";
import { postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import CustomRangePicker, { type CustomRange } from "./CustomRangePicker";
import type { QuizQuestion } from "@/lib/types";

interface AnswerResult { correct: boolean; answer: string; analysis?: string; }
interface GroupResult { questions: QuizQuestion[]; timed: boolean; total: number; }

export default function GroupQuizView() {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [limit, setLimit] = useState(10);
  const [timed, setTimed] = useState(false);
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<string[]>([]);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [timeoutMsg, setTimeoutMsg] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [startAt, setStartAt] = useState(Date.now());
  const submitRef = useRef<(a: string, c?: boolean) => void>(() => undefined);
  submitRef.current = submit;

  async function start(range: CustomRange) {
    setLoading(true);
    setError("");
    try {
      const res = await postJson<GroupResult>("/api/quiz/custom", {
        subjects: range.subjects, points: range.points, limit, timed,
      });
      setPickerOpen(false);
      if (!res.questions.length) {
        setError("所选范围暂无题目，请调整范围或题量。");
        setLoading(false);
        return;
      }
      setQuestions(res.questions);
      setIdx(0); setPicked([]); setResult(null);
      setStartAt(Date.now());
      setTimeoutMsg("");
      setSecondsLeft(res.timed ? res.questions.length * 60 : 0);
    } catch (e) {
      setError("组卷失败：" + String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!timed || !questions || idx >= questions.length) return;
    const timer = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(timer);
          if (!result) void submitRef.current("", true);
          setTimeoutMsg("时间到，已结束本组。");
          setIdx(questions.length);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [timed, questions, idx, result]);

  async function submit(answer: string, correctOverride?: boolean) {
    if (submitting || !questions) return;
    setSubmitting(true);
    try {
      const duration = Math.round((Date.now() - startAt) / 1000);
      const r = await postJson<AnswerResult>("/api/quiz/answer", {
        quiz_id: questions[idx].id, user_answer: answer,
        correct: correctOverride, duration_sec: duration,
      });
      setResult(r);
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    setPicked([]); setResult(null); setStartAt(Date.now());
    setIdx((i) => i + 1);
  }

  function toggle(letter: string) {
    if (result || !questions) return;
    const q = questions[idx];
    const isMulti = q.qtype === "choice" && q.answer.trim().length > 1;
    if (isMulti) {
      setPicked((p) => (p.includes(letter) ? p.filter((x) => x !== letter) : [...p, letter]));
    } else {
      setPicked([letter]);
      void submit(letter);
    }
  }

  if (!questions) {
    return (
      <div>
        <section className="card">
          <h2 className="card-title">智能组卷 / 限时模考</h2>
          <p className="muted">
            按科目或知识点自定义题量；开启限时后按「题数 × 60 秒」倒计时，时间到自动结束。
          </p>
          <label className="field">题量（1–50）
            <input type="number" min={1} max={50} value={limit}
              onChange={(e) => setLimit(Number(e.target.value))} />
          </label>
          <label className="check-row">
            <input type="checkbox" checked={timed}
              onChange={(e) => setTimed(e.target.checked)} />
            限时模考模式
          </label>
          <div className="row">
            <button className="btn btn-primary" disabled={loading}
              onClick={() => setPickerOpen(true)}>
              {loading ? "组卷中…" : "选择范围并开始"}
            </button>
          </div>
          {error && <p className="muted bad">{error}</p>}
        </section>
        <CustomRangePicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          onConfirm={(range) => void start(range)}
        />
      </div>
    );
  }

  if (idx >= questions.length) {
    return (
      <div className="card center">
        <h2>{timeoutMsg || "本组完成"}</h2>
        <p className="muted">共 {questions.length} 题，去「报告」看复盘。</p>
        <div className="row">
          <button className="btn" onClick={() => { setQuestions(null); setIdx(0); }}>
            再组一组
          </button>
        </div>
      </div>
    );
  }

  const q = questions[idx];
  const isMulti = q.qtype === "choice" && q.answer.trim().length > 1;
  const mm = Math.floor(secondsLeft / 60);
  const ss = secondsLeft % 60;
  return (
    <div>
      <div className="row group-head">
        <p className="muted">第 {idx + 1} / {questions.length} 题</p>
        {timed && (
          <span className={`badge${secondsLeft <= 60 ? " badge-red" : ""}`}>
            ⏱ {mm}:{String(ss).padStart(2, "0")}
          </span>
        )}
      </div>
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
                  <button key={opt} className={cls}
                    disabled={result !== null || submitting}
                    onClick={() => toggle(letter)}>
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
            {!result ? (
              <button className="btn btn-primary" onClick={() => setResult({ correct: false, answer: q.answer })}>
                显示答案
              </button>
            ) : (
              <div className="row">
                <button className="btn btn-good" disabled={submitting}
                  onClick={() => void submit("self", true)}>答对了</button>
                <button className="btn btn-bad" disabled={submitting}
                  onClick={() => void submit("self", false)}>答错了</button>
              </div>
            )}
          </div>
        )}
        {result && result.answer && (
          <div className={`result ${result.correct ? "ok" : "bad"}`}>
            <b>{result.correct ? "答对了" : "答错了"}</b>
            {q.qtype === "cloze" && <p className="muted">正确答案：{result.answer}</p>}
            <div className="analysis"
              dangerouslySetInnerHTML={{ __html: mdToHtml(result.analysis || `正确答案：${result.answer}`) }} />
            <button className="btn btn-ghost" onClick={next}>下一题</button>
          </div>
        )}
      </div>
    </div>
  );
}
