"""统计 data/entries/*.json（可叠加 SQLite）中各案例被引用的次数。

用法：
    python scripts/case_usage.py [--max N] [--db PATH]

默认扫描 data/entries/*.json；--db 可叠加 SQLite 中已入库条目的引用。
--max N（默认 0 = 不限制）：设置单案例引用上限，超过则打印告警并以退出码 1 结束。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app import importer  # noqa: E402


def _entries_from_json() -> list[dict]:
    entries = []
    entries_dir = config.DATA_DIR / "entries"
    for p in sorted(entries_dir.glob("*.json")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: {p} 解析失败: {exc}", file=sys.stderr)
            continue
        entries.extend(payload.get("entries", []))
    return entries


def _entries_from_db(db_path: Path) -> list[dict]:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT cases FROM entries").fetchall()
    conn.close()
    return [{"cases": json.loads(r["cases"] or "[]")} for r in rows]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="案例引用次数统计")
    ap.add_argument("--max", type=int, default=0, help="单案例引用上限（默认 0 = 不限制）")
    ap.add_argument("--db", help="额外叠加 SQLite 库中的引用")
    args = ap.parse_args(argv)

    entries = _entries_from_json()
    if args.db:
        entries.extend(_entries_from_db(Path(args.db)))
    counts = importer.count_case_refs(entries)
    if not counts:
        print("暂无案例引用")
        return 0
    total = sum(counts.values())
    limit = args.max if args.max else "不限"
    print(f"共引用 {total} 次，涉及 {len(counts)} 个案例（上限 {limit} 次/案例）")
    over = []
    for (source, loc), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][1])):
        flag = "  <-- 超上限" if args.max and n > args.max else ""
        print(f"  {n:>3}  {source}#{loc}{flag}")
        if args.max and n > args.max:
            over.append((source, loc, n))
    if over:
        print("存在超上限案例，请优先改配未引用案例", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
