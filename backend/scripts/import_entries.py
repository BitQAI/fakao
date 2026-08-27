"""导入 fakao-entry/1.0 侧车 JSON 到 SQLite。

用法：
    python scripts/import_entries.py 03_条目库/刑法.json [更多.json...]
退出码：0 = 全部成功；1 = 存在硬错误（整批拒绝）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app import importer  # noqa: E402


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("用法: python scripts/import_entries.py <json路径...>", file=sys.stderr)
        return 2
    conn = db.connect()
    failed = False
    for raw in args:
        path = Path(raw)
        try:
            result = importer.import_file(conn, path)
        except Exception as exc:  # noqa: BLE001 - CLI 兜底所有异常
            print(f"ERROR: {path} 导入失败: {exc}", file=sys.stderr)
            failed = True
            continue
        if result["errors"]:
            failed = True
            print(f"ERROR: {path} 校验失败（未入库）")
            for msg in result["errors"]:
                print(f"  - {msg}")
        else:
            print(f"OK: {path} 导入 {result['imported']} 条")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
