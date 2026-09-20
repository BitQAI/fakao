"""把 `data/quiz_bank/*.json` 幂等导入 `quizzes`（新机器/回滚后重建题库）。

幂等键复用 `quiz_bank.save_question`：同 (origin, qtype, entry_id/文本指纹, answer)
已存在就跳过，不覆盖库里已有的题（要覆盖加 `--replace`）。

用法：
    .venv/bin/python scripts/import_quiz_bank.py ../data/quiz_bank
    .venv/bin/python scripts/import_quiz_bank.py ../data/quiz_bank/*.json --replace
    .venv/bin/python scripts/import_quiz_bank.py ../data/quiz_bank --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, quiz_bank_io  # noqa: E402


def collect_files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            out += sorted(path.glob("*.json"))
        elif path.exists():
            out.append(path)
        else:
            print(f"跳过不存在的路径：{path}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从 data/quiz_bank 导入题库")
    ap.add_argument("paths", nargs="*", default=[str(Path(__file__).resolve().parents[2]
                                                   / "data" / "quiz_bank")],
                    help="题库 JSON 文件或目录（默认 ../data/quiz_bank）")
    ap.add_argument("--replace", action="store_true",
                    help="同 key 但内容不同时覆盖库中已有题（默认只跳过）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args(argv)

    files = collect_files(args.paths)
    if not files:
        print("没有可导入的题库文件")
        return 1
    conn = None if args.dry_run else db.connect()
    written = skipped = orphan = 0
    for path in files:
        payload = quiz_bank_io.parse(path.read_text(encoding="utf-8"))
        if conn is None:
            count = len(payload["items"])
            print(f"  [dry-run] {path.name}: {count} 题")
            written += count
            continue
        stats = quiz_bank_io.import_payload(conn, payload, replace=args.replace)
        written += stats["written"]
        skipped += stats["skipped"]
        orphan += stats["orphan"]
        print(f"  {path.name}: 写入 {stats['written']}，跳过 {stats['skipped']}"
              + (f"，条目缺失跳过 {stats['orphan']}" if stats["orphan"] else ""))
    if conn is not None:
        conn.close()
    print(f"{'待导入' if args.dry_run else '已导入'} {len(files)} 个文件，"
          f"写入 {written}，跳过 {skipped}"
          + (f"，条目缺失跳过 {orphan}（先导 entries）" if orphan else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
