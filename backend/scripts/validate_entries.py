"""导入前干跑校验条目 JSON：不写库，只报硬错误（E）与软警告（W）。

用法：
    python scripts/validate_entries.py ../data/entries/刑法.json [更多.json...]
退出码：0 = 全部通过（允许有警告）；1 = 存在硬错误；2 = 用法错误。

口径与 scripts/import_entries.py 完全一致（同一份 app/importer.check_payload），
区别只是不落库，用来回答「这批文件能不能顺利变成规范条目」。
详见 docs/superpowers/specs/2026-09-22-条目数据格式化元数据规范.md。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import importer  # noqa: E402


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("用法: python scripts/validate_entries.py <json路径...>", file=sys.stderr)
        return 2
    failed = False
    for raw in args:
        path = Path(raw)
        try:
            report = importer.check_payload(importer.load_payload(path))
        except Exception as exc:  # noqa: BLE001 - CLI 兜底所有异常
            print(f"ERROR: {path} 无法解析: {exc}", file=sys.stderr)
            failed = True
            continue
        errors, warnings = report["errors"], report["warnings"]
        if errors:
            failed = True
            print(f"FAIL: {path} 校验失败（{report['count']} 条，{len(errors)} 个硬错误）")
            for msg in errors:
                print(f"  E: {msg}")
        else:
            print(f"OK: {path} {report['count']} 条通过，{len(warnings)} 个警告")
        for msg in warnings:
            print(f"  W: {msg}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
