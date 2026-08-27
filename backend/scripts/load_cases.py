"""把案例库统一 JSONL 全文装载进 SQLite cases 表（幂等）。

用法：
    python scripts/load_cases.py

前置：data/案例库统一/documents/*.jsonl 存在（Task 0 format_cases.py 产出；
仓库已 gitignore，需在服务器上重新生成或随案例数据一起上传）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import cases, config, db  # noqa: E402


def main(argv=None) -> int:
    conn = db.connect()
    try:
        result = cases.ensure_cases_loaded(conn)
        print(f"OK: 案例装载完成，共 {result['loaded']} 条")
        if result["loaded"] == 0:
            print(f"提示: {config.CASES_DOCS_DIR} 下没有 JSONL，"
                  "请先运行 scripts/format_cases.py 生成。", file=sys.stderr)
            return 1
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
