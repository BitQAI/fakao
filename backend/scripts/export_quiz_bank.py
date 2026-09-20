"""把题库导出成 `data/quiz_bank/*.json`（可进版本库的资产）。

与 `data/entries/*.json` 同思路：按「origin + 科目」切分，每题一行，排序稳定。
只导出 online 题库（bank / judge）的 published 题；draft 是生成中间态、
archived 是下架题、daily 是当日缓存，都不入库。

用法：
    .venv/bin/python scripts/export_quiz_bank.py
    .venv/bin/python scripts/export_quiz_bank.py --origins bank --dry-run
    .venv/bin/python scripts/export_quiz_bank.py --out /tmp/qb --statuses draft
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, quiz_bank_io  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="导出题库到 data/quiz_bank")
    ap.add_argument("--out", default=str(config.DATA_DIR / "quiz_bank"))
    ap.add_argument("--origins", default="bank,judge")
    ap.add_argument("--statuses", default="published")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    origins = tuple(x.strip() for x in args.origins.split(",") if x.strip())
    statuses = tuple(x.strip() for x in args.statuses.split(",") if x.strip())
    conn = db.connect()
    result = quiz_bank_io.export(conn, Path(args.out), origins, statuses,
                                 dry_run=args.dry_run)
    conn.close()
    for f in result["files"]:
        print(f"  {f['count']:5d}  {f['path']}")
    print(f"{'将导出' if args.dry_run else '已导出'} {result['total']} 题，"
          f"{len(result['files'])} 个文件 -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
