"""听学音频修复：对缺失/空/陈旧/语速异常的条目重合成，并补全台账。

用法（默认 dry-run，不动文件）：
    .venv/bin/python scripts/repair_tts.py                     # 列出待修复清单
    .venv/bin/python scripts/repair_tts.py --apply             # 执行修复
    .venv/bin/python scripts/repair_tts.py --apply --ids SJ-677,SG-339
    .venv/bin/python scripts/repair_tts.py --apply --backfill  # 仅给健康文件补台账
    .venv/bin/python scripts/repair_tts.py --kind card         # 法条题卡档（只修坏录音）

安全设计：先取到新音频（内存）才覆盖旧文件——合成失败时旧音频保留，不会失声。
默认 --kind entry；卡片档不会因「缺音频」批量合成（那是 synthesize_cards.py 的职责）。
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, tts, tts_audit  # noqa: E402

WORKERS = 3


def _entries(conn, ids: list[str] | None, kind: str = "entry"):
    if kind == "entry":
        sql = ("SELECT id, tts_text FROM v_entries"
               " WHERE status='final' AND tts_text != ''")
    else:
        sql = ("SELECT id, tts_text FROM entries"
               " WHERE status='final' AND tts_text != ''")
        if kind == "card":
            sql += " AND kind='card'"
    params: tuple = ()
    if ids:
        sql += " AND id IN (%s)" % ",".join("?" * len(ids))
        params = tuple(ids)
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def _render(item: tuple[str, str]) -> tuple[str, bytes | None]:
    entry_id, text = item
    return entry_id, tts.render_audio(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="听学音频修复（默认 dry-run）")
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只打印计划）")
    ap.add_argument("--ids", default=None, help="只处理指定条目，逗号分隔")
    ap.add_argument("--backfill", action="store_true",
                    help="只补台账（不重合成）；与 --apply 同用")
    ap.add_argument("--fast", action="store_true", help="质检跳过波形扫描")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--kind", choices=("entry", "card", "all"), default="entry",
                    help="修复范围：entry 正式条目（默认）/ card 法条题卡 / all")
    args = ap.parse_args(argv)

    ids = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else None
    conn = db.connect()
    rows = _entries(conn, ids, args.kind)
    texts = {r["id"]: r["tts_text"] for r in rows}

    if args.backfill:
        existing = {r["entry_id"] for r in conn.execute("SELECT entry_id FROM tts_assets")}
        todo = [r for r in rows if (config.AUDIO_DIR / f"{r['id']}.wav").exists()
                and r["id"] not in existing]
        print(f"待建档 {len(todo)} 条 / 扫描 {len(rows)} 条")
        if args.apply:
            for r in todo:
                tts.record_asset(conn, r["id"], texts[r["id"]],
                                 config.AUDIO_DIR / f"{r['id']}.wav")
            print(f"已建档 {len(todo)} 条")
        conn.close()
        return 0

    max_duration = (tts_audit.MAX_CARD_DURATION_SEC if args.kind == "card" else 0.0)
    issues = tts_audit.audit_entries(conn, rows, wave_metrics=not args.fast,
                                     max_duration_sec=max_duration)
    repair_kinds = (tts_audit.CARD_REPAIR_KINDS if args.kind == "card"
                    else tts_audit.DEFAULT_REPAIR_KINDS)
    summary = tts_audit.summarize(issues, repair_kinds=repair_kinds)
    targets = sorted({i.strip() for i in (ids or [])} | set(summary["repair_ids"]))
    print("质检汇总：" + "，".join(f"{k} {v}" for k, v in summary["counts"].items()))
    print(f"待重合成 {len(targets)} 条"
          + (f"：{' '.join(targets[:20])}" if targets else ""))
    if not args.apply:
        print("（dry-run，未改动文件；加 --apply 执行）")
        conn.close()
        return 0

    todo = [(i, texts[i]) for i in targets if i in texts]

    def duration(entry_id: str) -> float:
        return tts.audio_duration_sec(config.AUDIO_DIR / f"{entry_id}.wav")

    before = {entry_id: duration(entry_id) for entry_id, _ in todo}
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for entry_id, content in pool.map(_render, todo):
            if not content:
                fail += 1
                print(f"  FAIL {entry_id}（模型链不可用，旧音频保留）")
                continue
            path = config.AUDIO_DIR / f"{entry_id}.wav"
            path.write_bytes(content)
            tts.record_asset(conn, entry_id, texts[entry_id], path)
            ok += 1
            print(f"  OK   {entry_id} {before[entry_id]}s -> "
                  f"{tts.audio_duration_sec(path)}s")
    print(f"完成：成功 {ok}，失败 {fail}")
    conn.close()
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
