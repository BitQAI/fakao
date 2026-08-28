"""批量合成全部 final 条目的听学音频（幂等，已存在非空 wav 跳过）。

用法：
    python scripts/synthesize_audio.py                # 全量
    python scripts/synthesize_audio.py --id XF-001    # 单条
    python scripts/synthesize_audio.py --dry-run      # 只看待合成清单
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, tts  # noqa: E402


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    only_id = None
    dry_run = False
    retries = 2
    for a in args:
        if a == "--dry-run":
            dry_run = True
        elif a.startswith("--id="):
            only_id = a.split("=", 1)[1]
        elif a.startswith("--retries="):
            retries = int(a.split("=", 1)[1])

    conn = db.connect()
    sql = "SELECT id, tts_text FROM entries WHERE status='final' AND tts_text != ''"
    params: tuple = ()
    if only_id:
        sql += " AND id=?"
        params = (only_id,)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    todo = []
    for r in rows:
        path = tts.ensure_mp3(r["id"], r["tts_text"], dry_run=True)
        if not path.exists() or path.stat().st_size == 0:
            todo.append(r["id"])
    print(f"待合成 {len(todo)} 条 / 共 {len(rows)} 条"
          + ("" if not only_id else f"（筛选 {only_id}）"))
    if dry_run:
        return 0

    ok = fail = 0
    for i, entry_id in enumerate(todo, 1):
        text = next(r["tts_text"] for r in rows if r["id"] == entry_id)
        for attempt in range(retries + 1):
            out = tts.ensure_mp3(entry_id, text)
            if out.exists() and out.stat().st_size > 0:
                ok += 1
                print(f"[{i}/{len(todo)}] OK  {entry_id} "
                      f"({out.stat().st_size // 1024}KB, 第{attempt + 1}次)")
                break
            if attempt < retries:
                time.sleep(1)
        else:
            fail += 1
            print(f"[{i}/{len(todo)}] FAIL {entry_id}（模型链全部不可用）")
    print(f"完成：成功 {ok}，失败 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
