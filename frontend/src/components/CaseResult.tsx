"use client";
import type { CaseGrade, EssayMetrics } from "@/lib/caseTypes";

interface Props {
  grade: CaseGrade;
  onNext: () => void;
}

/** 判分结果：按维度看失分结构 + 论述题形式检查 + 未命中采分点（带法条直达）。 */
export default function CaseResult({ grade, onNext }: Props) {
  return (
    <div className="case-result">
      <div className="card">
        <h3>得分 {grade.score}（命中 {grade.hit.length}/{grade.total}）</h3>
        <div className="kind-stats">
          {grade.by_kind.map((k) => (
            <span key={k.kind}
              className={`kind-stat${k.hit === k.total ? " full" : ""}`}>
              {k.kind} {k.hit}/{k.total}
            </span>
          ))}
        </div>
        <p className="muted">参考答案：{grade.reference}</p>
      </div>

      {grade.essay && <EssayCheck metrics={grade.essay} />}

      {grade.missed.length > 0 && (
        <div className="card">
          <b>未命中的采分点（{grade.missed.length}）</b>
          {grade.missed.map((m) => (
            <div key={m.no} className="case-missed">
              <p>
                {m.qno ? <span className="qno-tag">第{m.qno}问</span> : null}
                <span className="kind-badge">{m.kind}</span>{m.text}
              </p>
              {m.links.map((l) => (
                <button key={l.ref} className="chip"
                  onClick={() => { window.location.href = l.url; }}>
                  看依据：{l.ref}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
      <button className="btn btn-ghost" onClick={onNext}>下一题</button>
    </div>
  );
}

/** 论述题形式检查：字数与是否大段照搬材料（都不靠模型判断）。 */
function EssayCheck({ metrics }: { metrics: EssayMetrics }) {
  const ok = metrics.verdict.length === 0;
  return (
    <div className={`card essay-check${ok ? "" : " warn"}`}>
      <b>形式检查</b>
      <div className="essay-metrics">
        <span className={metrics.reach ? "ok" : "bad"}>
          字数 {metrics.chars} / {metrics.min_chars}
        </span>
        <span className={metrics.copied ? "bad" : "ok"}>
          照搬材料 {Math.round(metrics.copy_ratio * 100)}%
          （红线 {Math.round(metrics.copy_limit * 100)}%）
        </span>
      </div>
      {ok ? (
        <p className="hint">字数与原创性都过关，接下来看内容维度有没有丢分。</p>
      ) : (
        <ul className="essay-verdict">
          {metrics.verdict.map((v) => <li key={v}>{v}</li>)}
        </ul>
      )}
    </div>
  );
}
