"""把已发布的法条驱动题重建为卡片条目（entries.kind='card'，幂等）。

卡片是题库的派生数据：题库每次 `--publish` 后重跑本脚本即可。
文本漂移会同步更新并作废旧音频；题库下架的题，对应卡片转 draft（不进队列）。

用法：
    .venv/bin/python scripts/sync_card_entries.py --dry-run
    .venv/bin/python scripts/sync_card_entries.py
    .venv/bin/python scripts/sync_card_entries.py --subject 刑法
    .venv/bin/python scripts/sync_card_entries.py --db /tmp/copy.db
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import card_entries, db  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="法条题卡条目化（幂等重建）")
    ap.add_argument("--subject", action="append",
                    help="只同步指定科目（可多次；不传=全部）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 题（调试）")
    ap.add_argument("--db", default=None, help="数据库路径（默认 data/fakao.db）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    try:
        counts = card_entries.sync(conn, subjects=args.subject, limit=args.limit,
                                   dry_run=args.dry_run)
        stats = card_entries.stats(conn)
    finally:
        conn.close()

    tag = "（dry-run，未写库）" if args.dry_run else ""
    print(f"题库已发布法条驱动题 {counts['total']} 条{tag}")
    print(f"新建 {counts['created']} · 更新 {counts['updated']} · "
          f"无变化 {counts['unchanged']} · 清理 {counts['cleaned']}（下架转 draft / 非客观题删除）")
    print(f"卡片条目 {stats['cards']} 张（final {stats['final']}）· "
          f"正式条目 {stats['entries']} 条 · 题库应覆盖 {stats['published']} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
