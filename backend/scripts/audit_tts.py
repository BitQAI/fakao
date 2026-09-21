"""听学音频质检：列出缺失 / 空文件 / 陈旧 / 语速异常 / 未登记 五类问题。

用法：
    .venv/bin/python scripts/audit_tts.py                 # 全量（含波形指标）
    .venv/bin/python scripts/audit_tts.py --fast          # 跳过 RMS/静音扫描
    .venv/bin/python scripts/audit_tts.py --kind card     # 法条题卡档
    .venv/bin/python scripts/audit_tts.py --json out.json # 输出机器可读结果
    .venv/bin/python scripts/audit_tts.py --report docs/superpowers/research/x.md

判定口径见 app/tts_audit.py 模块头。默认 --kind entry（正式条目，走 v_entries）；
卡片档（--kind card）把 missing 记为「待生成」（按需合成，非故障），不驱动重合成。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, tts_audit  # noqa: E402

KIND_LABEL = {"entry": "正式条目", "card": "法条题卡", "all": "全部（条目+卡片）"}
SAMPLE_PER_KIND = 15


def _rows(conn, kind: str = "entry"):
    if kind == "entry":
        return conn.execute(
            "SELECT id, tts_text FROM v_entries WHERE status='final' AND tts_text != ''"
            " ORDER BY id").fetchall()
    sql = ("SELECT id, tts_text FROM entries"
           " WHERE status='final' AND tts_text != ''")
    if kind == "card":
        sql += " AND kind='card'"
    return conn.execute(sql + " ORDER BY id").fetchall()


def _report_markdown(summary: dict, issues, wave_metrics: bool,
                     kind: str = "entry") -> str:
    lines = [
        "# 听学音频质检报告（自动生成）",
        "",
        f"- 扫描范围：final {KIND_LABEL.get(kind, kind)} {summary['scanned']} 条；"
        f"{'含波形指标（RMS/首尾静音）' if wave_metrics else '仅时长与台账（--fast）'}",
        f"- 判定口径：语速 <{tts_audit.MIN_RATE} 或 >{tts_audit.MAX_RATE} 字/秒为异常"
        "（实测中位 4.81，>6.5 为截断）；整体 RMS <"
        f"{tts_audit.SILENT_OVERALL_RMS} 视为无声；首/尾静音 >"
        f"{tts_audit.MAX_EDGE_SILENCE_SEC} 秒为异常。",
        "",
        "## 汇总",
        "",
        "| 类型 | 数量 |",
        "|---|---:|",
    ]
    for kind, n in summary["counts"].items():
        lines.append(f"| {kind} | {n} |")
    lines += ["", f"**需重合成：{len(summary['repair_ids'])} 条**", ""]
    for kind, ids in summary["ids"].items():
        if not ids:
            continue
        lines += [f"### {kind}（{len(ids)} 条）", "",
                  "```", " ".join(ids[:60]), "```", ""]
    detail = [i for i in issues if i.kind in ("stale", "suspect")]
    if detail:
        lines += ["## 逐条明细（stale / suspect）", "",
                  "| 条目 | 类型 | 说明 | 字数 | 时长(s) | 字/秒 | RMS |",
                  "|---|---|---|---:|---:|---:|---:|"]
        for i in detail[:200]:
            lines.append(f"| {i.entry_id} | {i.kind} | {i.detail} | {i.chars} |"
                         f" {i.duration_sec} | {i.chars_per_sec} | {i.rms} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="听学音频质检")
    ap.add_argument("--fast", action="store_true", help="跳过 RMS/静音扫描（只查时长与台账）")
    ap.add_argument("--kind", choices=("entry", "card", "all"), default="entry",
                    help="扫描范围：entry 正式条目（默认）/ card 法条题卡 / all")
    ap.add_argument("--limit", type=int, default=0, help="只扫描前 N 条（调试用）")
    ap.add_argument("--json", default=None, help="把完整结果写为 JSON")
    ap.add_argument("--report", default=None, help="把 Markdown 报告写到该路径")
    args = ap.parse_args(argv)

    conn = db.connect()
    rows = _rows(conn, args.kind)
    max_duration = (tts_audit.MAX_CARD_DURATION_SEC if args.kind == "card" else 0.0)
    issues = tts_audit.audit_entries(conn, rows, wave_metrics=not args.fast,
                                     limit=args.limit, max_duration_sec=max_duration)
    repair_kinds = (tts_audit.CARD_REPAIR_KINDS if args.kind == "card"
                    else tts_audit.DEFAULT_REPAIR_KINDS)
    summary = tts_audit.summarize(issues, repair_kinds=repair_kinds)
    summary["scanned"] = min(len(rows), args.limit) if args.limit else len(rows)
    print(f"扫描 {summary['scanned']} 条（{KIND_LABEL.get(args.kind, args.kind)}）："
          + "，".join(f"{k} {v}" for k, v in summary["counts"].items()))
    print(f"需重合成 {len(summary['repair_ids'])} 条"
          + (f"：{' '.join(summary['repair_ids'][:20])}"
             if summary["repair_ids"] else ""))
    if args.kind == "card":
        print(f"待生成（按需合成的正常状态）{summary['counts'].get('missing', 0)} 条")
    stale = [i for i in issues if i.kind in ("stale", "suspect")]
    for i in stale[:SAMPLE_PER_KIND]:
        print(f"  - {i.entry_id} {i.kind} {i.detail} "
              f"({i.chars}字/{i.duration_sec}s={i.chars_per_sec}字每秒)")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"summary": summary, "issues": [i.to_dict() for i in issues]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON -> {args.json}")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            _report_markdown(summary, issues, not args.fast, args.kind),
            encoding="utf-8")
        print(f"报告 -> {args.report}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
