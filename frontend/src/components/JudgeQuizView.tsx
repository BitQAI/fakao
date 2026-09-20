"use client";
import { useEffect, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import { mdToHtml } from "@/lib/md";
import type { QuizQuestion } from "@/lib/types";

interface AnswerResult { correct: boolean; answer: string; analysis?: string; }
interface JudgeResult { questions: QuizQuestion[]; total: number; }

const SUBJECTS = ["刑法", "民法", "刑诉", "民诉", "行政法", "商经知劳环", "理论法", "三国法"];

export default function JudgeQuizView() {
  const [subjects, setSubjects] = useState<string[]>([]);
  const [limit, setLimit] = useState(10);
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [resultMap, setResultMap] = useState<Record<number, AnswerResult>>({});
  const [pickMap, setPickMap] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [start, setStart] = useState(Date.now());
  const [bankCount, setBankCount] = useState<number | null>(null);

  useEffect(() => {
    getJson<{ items: { origin: string; status: string; n: number }[] }>("/api/quiz/bank/stats")
      .then((d) => setBankCount(d.items
        .filter((i) => i.origin === "judge" && i.status === "published")
        .reduce((sum, i) => sum + i.n, 0)))
      .catch(() => setBankCount(null));
  }, []);

  function toggleSubject(s: string) {
    setSubjects((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  }

  async function startQuiz() {
    setLoading(true);
    setError("");
    try {
      const res = await postJson<JudgeResult>("/api/quiz/judge", {
        subjects, points: [], limit,
      });
      setQuestions(res.questions);
      setIdx(0);
      setResult(null);
      setResultMap({});
      setPickMap({});
      setStart(Date.now());
    } catch (e) {
      setError("抽题失败：" + String(e));
    } finally {
      setLoading(false);
    }
  }

  async function answer(pick: "对" | "错") {
    if (!questions || result) return;
    const q = questions[idx];
    setPickMap((m) => ({ ...m, [idx]: pick }));
    const r = await postJson<AnswerResult>("/api/quiz/answer", {
      quiz_id: q.id, user_answer: pick,
      duration_sec: Math.round((Date.now() - start) / 1000),
    });
    setResult(r);
    setResultMap((m) => ({ ...m, [idx]: r }));
  }

  function goNext() {
    const nid = idx + 1;
    setIdx(nid);
    setResult(resultMap[nid] || null);
    setStart(Date.now());
  }

  function goPrev() {
    if (idx === 0) return;
    const nid = idx - 1;
    setIdx(nid);
    setResult(resultMap[nid] || null);
  }

  if (!questions) {
    return (
      <section className="card">
        <h2 className="card-title">数判 · 数量金额年限专项</h2>
        <p className="muted">
          只考「数」——期限、金额、人数、数量、比例。逐题判对错，错了立刻看正确值与法条依据。
          {bankCount !== null && ` 当前题库 ${bankCount} 题。`}
        </p>
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          <button className={`segment${subjects.length === 0 ? " active" : ""}`}
            onClick={() => setSubjects([])}>全部科目</button>
          {SUBJECTS.map((s) => (
            <button key={s} className={`segment${subjects.includes(s) ? " active" : ""}`}
              onClick={() => toggleSubject(s)}>{s}</button>
          ))}
        </div>
        <label className="field">题量（1–50）
          <input type="number" min={1} max={50} value={limit}
            onChange={(e) => setLimit(Number(e.target.value))} />
        </label>
        <div className="row">
          <button className="btn btn-primary" disabled={loading} onClick={() => void startQuiz()}>
            {loading ? "抽题中…" : "开始数判"}
          </button>
        </div>
        {error && <p className="muted bad">{error}</p>}
        {bankCount === 0 && (
          <p className="muted">
            题库还没有内容：运行 <code>backend/scripts/build_judge_bank.py</code> 生成后，
            在「我的 → 数据」重新发布即可。
          </p>
        )}
      </section>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="card">
        <h2>这个范围还没有数字题</h2>
        <p className="muted">换个科目，或先生成题库（scripts/build_judge_bank.py）。</p>
        <button className="btn" onClick={() => setQuestions(null)}>返回</button>
      </div>
    );
  }

  if (idx >= questions.length) {
    const answered = questions.filter((q) => resultMap[q.id] !== undefined).length;
    const right = questions.filter((q) => resultMap[q.id]?.correct).length;
    return (
      <div className="card center">
        <h2>本组完成</h2>
        <p className="muted">答对 {right} / {answered} 题
          {answered > 0 && `（正确率 ${Math.round((right / answered) * 100)}%）`}
        </p>
        <div className="row">
          <button className="btn" onClick={() => {
            setQuestions(null); setIdx(0); setResult(null);
            setResultMap({}); setPickMap({});
          }}>再来一组</button>
        </div>
      </div>
    );
  }

  const q = questions[idx];
  return (
    <div>
      <div className="row group-head">
        <p className="muted">第 {idx + 1} / {questions.length} 题</p>
        {q.subject && <span className="badge">{q.subject}{q.point ? ` · ${q.point}` : ""}</span>}
      </div>
      <div className="card">
        <h3>{q.stem}</h3>
        {!result ? (
          <div className="row">
            <button className="btn btn-good" onClick={() => void answer("对")}>✓ 对</button>
            <button className="btn btn-bad" onClick={() => void answer("错")}>✗ 错</button>
          </div>
        ) : (
          <div className={`result ${result.correct ? "ok" : "bad"}`}>
            <b>{result.correct ? "判断正确" : "判断错误"}</b>
            <p className="muted">
              你的答案：{pickMap[idx]} · 正确答案：{result.answer}
              {q.basis ? ` · 依据 ${q.basis}` : ""}
            </p>
            <div className="analysis"
              dangerouslySetInnerHTML={{ __html: mdToHtml(result.analysis || `正确答案：${result.answer}`) }} />
          </div>
        )}
        <div className="row">
          {result && <button className="btn btn-ghost" onClick={goNext}>下一题</button>}
          {idx > 0 && <button className="btn btn-ghost" onClick={goPrev}>上一题</button>}
        </div>
      </div>
    </div>
  );
}
