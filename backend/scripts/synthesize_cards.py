"""法条题卡听学音频：预热听学队列头部 / 全量分片合成（幂等，可中断续跑）。

卡片（`entries.kind='card'`）以按需合成为主，本脚本负责两件事：

1. **预热**（方案 A）：按听学队列顺序，把马上会听到的那批卡片先合成掉；
2. **全量**：支持 `--shard I/N` 分片，交给多个进程/多个 agent 并行跑，
   分片互不重叠、天然幂等（已存在非空 wav 直接跳过）。

用法：
    .venv/bin/python scripts/synthesize_cards.py --queue 200 --dry-run
    .venv/bin/python scripts/synthesize_cards.py --queue 200
    .venv/bin/python scripts/synthesize_cards.py --all --shard 1/3 --workers 16
    .venv/bin/python scripts/synthesize_cards.py --ids XF-Q003841,XF-Q003842
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, service, tts  # noqa: E402

WORKERS = 8
RETRIES = 2


def _audio_entry_ids() -> set[str]:
    """已有可用音频的 ID 集合（目录扫描一次，避免逐条 stat）。"""
    try:
        return {p.stem for p in config.AUDIO_DIR.glob("*.wav") if p.stat().st_size > 0}
    except OSError:
        return set()


def _card_rows(conn, *, subjects: list[str] | None = None,
               ids: list[str] | None = None):
    sql = ("SELECT id, tts_text FROM entries WHERE kind='card'"
           " AND status='final' AND tts_text != ''")
    params: list = []
    if subjects:
        sql += f" AND subject IN ({','.join('?' * len(subjects))})"
        params += subjects
    if ids:
        sql += f" AND id IN ({','.join('?' * len(ids))})"
        params += ids
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def pick_targets(rows, have: set[str], *, queue_ids: list[str] | None = None,
                 shard: tuple[int, int] | None = None,
                 limit: int = 0) -> list[tuple[str, str]]:
    """挑出待合成 (id, text)：先按队列顺序（预热）或 id 顺序（全量），再分片截断。"""
    by_id = {r["id"]: r["tts_text"] for r in rows}
    if queue_ids is not None:
        todo = [(i, by_id[i]) for i in queue_ids if i in by_id and i not in have]
    else:
        todo = [(r["id"], r["tts_text"]) for r in rows if r["id"] not in have]
        if shard:
            idx, total = shard
            todo = todo[idx - 1::total]
    return todo[:limit] if limit else todo


def _render(item: tuple[str, str], retries: int) -> tuple[str, bytes | None]:
    """只做网络合成（线程池内跑），落盘与台账留在主线程，避开 SQLite 多线程写。"""
    entry_id, text = item
    for attempt in range(retries + 1):
        content = tts.render_audio(text)
        if content:
            return entry_id, content
        if attempt < retries:
            time.sleep(1)
    return entry_id, None


def _parse_shard(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    idx, _, total = raw.partition("/")
    idx, total = int(idx), int(total)
    if total < 1 or not 1 <= idx <= total:
        raise SystemExit(f"--shard 非法：{raw}（应为 I/N，1<=I<=N）")
    return idx, total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="法条题卡音频：预热 / 全量分片合成")
    ap.add_argument("--queue", type=int, default=0,
                    help="预热听学队列前 N 张卡片（缺音频的才合成）")
    ap.add_argument("--all", action="store_true", help="全量：所有缺音频的卡片")
    ap.add_argument("--shard", default=None, help="分片 I/N，供多进程/多 agent 并行")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--retries", type=int, default=RETRIES)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（调试）")
    ap.add_argument("--subject", action="append", help="只看指定科目（可多次）")
    ap.add_argument("--ids", default=None, help="指定卡片 ID，逗号分隔")
    ap.add_argument("--dry-run", action="store_true", help="只列清单，不合成")
    args = ap.parse_args(argv)

    ids = [x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else None
    if not (args.queue or args.all or ids):
        ap.error("请指定 --queue N（预热）、--all（全量）或 --ids")
    shard = _parse_shard(args.shard)
    if shard and not args.all:
        ap.error("--shard 只用于 --all 全量分片")

    conn = db.connect()
    try:
        have = _audio_entry_ids()
        rows = _card_rows(conn, subjects=args.subject, ids=ids)
        queue_ids = None
        if args.queue:
            # 排除已有音频后再排序：否则前 N 里被已合成卡片占位，实际预热不足
            queue_ids = service.listen_card_ids(conn, limit=args.queue * 4, exclude=have)
        todo = pick_targets(rows, have, queue_ids=queue_ids, shard=shard,
                           limit=args.limit)
        if args.queue:
            todo = todo[:args.queue]
        chars = sum(len(t) for _, t in todo)
        scope = (f"听学队列前 {args.queue} 张" if args.queue
                 else f"全量分片 {shard[0]}/{shard[1]}" if shard else "全量")
        print(f"{scope}：卡片 {len(rows)} 张，已有音频 {len(have & {r['id'] for r in rows})} 张，"
              f"待合成 {len(todo)} 张（{chars} 字）")
        if args.dry_run or not todo:
            print("（dry-run，未合成）" if args.dry_run else "（无待合成项）")
            return 0

        config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ok = fail = 0
        started = time.time()
        texts = dict(todo)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for i, (entry_id, content) in enumerate(
                    pool.map(lambda it: _render(it, args.retries), todo), 1):
                if not content:
                    fail += 1
                    print(f"[{i}/{len(todo)}] FAIL {entry_id}（模型链不可用）")
                    continue
                path = config.AUDIO_DIR / f"{entry_id}.wav"
                path.write_bytes(content)
                tts.record_asset(conn, entry_id, texts[entry_id], path)
                ok += 1
                if i % 20 == 0 or i == len(todo):
                    rate = i / max(time.time() - started, 0.1)
                    print(f"[{i}/{len(todo)}] OK  最近 {entry_id}，"
                          f"均速 {rate:.2f} 张/秒，已用 {(time.time() - started) / 60:.1f} 分钟")
        print(f"完成：成功 {ok}，失败 {fail}，耗时 {(time.time() - started) / 60:.1f} 分钟")
        return 1 if fail else 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
