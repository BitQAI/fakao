"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson } from "@/lib/api";
import type {
  CaseDetail, CaseGrade, CaseQuestion, CaseQType, CaseStats,
} from "@/lib/caseTypes";
import CaseCheckPanel from "./CaseCheckPanel";
import CaseResult from "./CaseResult";

const DEFAULT_LIMIT = 600;  // 超时只提示，不阻断

type Stage = "answer" | "check" | "done";

/** 主观题作答：写要点 / 只听 → 采分点核对 → 得分与未命中点。 */
export default function CaseView({ type = "case" }: { type?: CaseQType }) {
  const [q, setQ] = useState<CaseQuestion | null>(null);
  const [stats, setStats] = useState<CaseStats | null>(null);
  const [mode, setMode] = useState<"write" | "listen">("write");
  const [stage, setStage] = useState<Stage>("answer");
  const [text, setText] = useState("");
  const [points, setPoints] = useState<CaseDetail["points"]>([]);
  const [hit, setHit] = useState<Set<number>>(new Set());
  const [grade, setGrade] = useState<CaseGrade | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [listened, setListened] = useState(false);
  const timer = useRef<number | null>(null);

  const load = useCallback(() => {
    setStage("answer"); setText(""); setHit(new Set()); setGrade(null);
    setElapsed(0); setListened(false);
    getJson<{ question: CaseQuestion | null; stats: CaseStats }>(
      `/api/cases/daily?type=${type}`)
      .then((d) => { setQ(d.question); setStats(d.stats); });
  }, [type]);
  useEffect(load, [load]);

  useEffect(() => {
    if (stage !== "answer") return;
    timer.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [stage]);

  async function submit() {
    if (!q || busy) return;
    setBusy(true);
    try {
      const d = await postJson<{ points: CaseDetail["points"] }>(
        `/api/cases/${q.id}/answer`,
        { answer_text: text, duration_sec: elapsed, mode });
      setPoints(d.points);
      setStage("check");
    } finally {
      setBusy(false);
    }
  }

  async function doGrade() {
    if (!q || busy) return;
    setBusy(true);
    try {
      const d = await postJson<CaseGrade>(`/api/cases/${q.id}/grade`,
        { hit_points: Array.from(hit) });
      setGrade(d);
      setStage("done");
    } finally {
      setBusy(false);
    }
  }

  if (!q) return <p className="muted">这一类还没有已发布的题目。</p>;
  const limit = (q.slot?.minutes || 0) * 60 || DEFAULT_LIMIT;
  const overtime = elapsed > limit;
  const isEssay = q.qtype === "essay";
  const chars = countChars(text);
  const minChars = q.spec?.min_chars ?? 0;

  return (
    <div className="case-view">
      <div className="case-head">
        <span className="priority-badge">{q.subject}</span>
        {q.slot && q.slot.slot > 0 && (
          <span className="tag">
            {q.slot.label} · 建议 {q.slot.minutes} 分钟 / {q.slot.score} 分
          </span>
        )}
        <span className="muted">{q.case?.title}</span>
      </div>

      {stage === "answer" && (
        <>
          <div className="mode-row">
            <button className={`mode-btn${mode === "write" ? " active" : ""}`}
              onClick={() => setMode("write")}>{isEssay ? "写全文" : "写要点"}</button>
            <button className={`mode-btn${mode === "listen" ? " active" : ""}`}
              onClick={() => { setMode("listen"); setListened(false); }}>
              {isEssay ? "只读不听" : "只听"}
            </button>
            <span className={`muted${overtime ? " bad" : ""}`}>
              {fmt(elapsed)}{overtime ? `（已超建议 ${q.slot?.minutes} 分钟）` : ""}
            </span>
          </div>

          {(q.materials?.length ?? 0) > 0 && (
            <div className="case-materials">
              {q.materials!.map((m) => (
                <div key={m.label} className="case-material">
                  <span className="material-label">{m.label}</span>
                  <p>{m.text}</p>
                </div>
              ))}
            </div>
          )}

          <div className="card case-stem">
            <p>{q.stem}</p>
            <ol className="case-questions">
              {q.questions.map((item, i) => <li key={i}>{item}</li>)}
            </ol>
          </div>

          {q.skeleton && q.skeleton.length > 0 && (
            <details className="case-skeleton">
              <summary>作答骨架：{q.spec?.label ?? "案例分析"}（点开对照，别照抄）</summary>
              <ol>
                {q.skeleton.map((s, i) => <li key={i}>{s}</li>)}
              </ol>
            </details>
          )}

          {mode === "write" ? (
            <>
              <textarea className="case-input" rows={isEssay ? 16 : 7} value={text}
                placeholder={isEssay
                  ? "按「总论点 → 理论依据 → 结合材料 → 实践措施 → 升华」写全文，600 字以上…"
                  : "按「结论 + 依据」写要点，写不到的点留空也行…"}
                onChange={(e) => setText(e.target.value)} />
              {isEssay && (
                <p className={`char-count${minChars && chars >= minChars ? " ok" : ""}`}>
                  {chars} 字 / 下限 {minChars} 字
                  {q.spec?.advise_chars ? `（建议 ${q.spec.advise_chars} 字）` : ""}
                  {" ｜ 别照抄材料原文，照抄的论述阅卷时不计分"}
                </p>
              )}
            </>
          ) : (
            <div className="card">
              <audio controls src={`/api/cases/${q.id}/audio`}
                onEnded={() => setListened(true)}
                onError={() => setListened(true)}
                style={{ width: "100%" }} />
              <p className="hint">
                只朗读题干与设问，不读答案；听完才能进入采分点核对，
                否则这条不计入今日进度（避免退化成纯听）。
              </p>
            </div>
          )}

          <button className="btn btn-primary"
            disabled={busy || (mode === "listen" && !listened)}
            onClick={submit}>
            {mode === "listen"
              ? (listened ? "我去核对采分点" : "先听完音频再核对")
              : (busy ? "提交中…" : "提交并核对采分点")}
          </button>
        </>
      )}

      {stage === "check" && (
        <CaseCheckPanel points={points} hit={hit} busy={busy}
          onToggle={(no) => setHit((s) => toggle(s, no))} onSubmit={doGrade} />
      )}

      {stage === "done" && grade && (
        <CaseResult grade={grade} onNext={load} />
      )}

      {stats && (
        <p className="muted">
          已做 {stats.questions_done}/{stats.published} 题
          {stats.by_subject.length > 0 && " ｜ " + stats.by_subject
            .map((s) => `${s.subject} 均分 ${s.avg}`).join("，")}
        </p>
      )}
    </div>
  );
}

function toggle(set: Set<number>, n: number) {
  const next = new Set(set);
  if (next.has(n)) next.delete(n); else next.add(n);
  return next;
}

function fmt(sec: number) {
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 与后端 subjective_templates.squash 同口径：只数汉字与字母数字，标点空格不计。 */
export function countChars(text: string) {
  return (text.match(/[0-9A-Za-z\u4e00-\u9fff]/g) ?? []).length;
}
