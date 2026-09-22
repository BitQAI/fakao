"""把批次条目文件合并进 data/entries/<科目>.json（幂等，按 id + point 去重）。

用法：
    python scripts/merge_entry_batch.py ../data/batches/<批次>/entries/*.json            # dry-run
    python scripts/merge_entry_batch.py ../data/batches/<批次>/entries/*.json --apply
退出码：0 = 成功；1 = 存在无法合并的文件；2 = 用法错误。

为什么需要它：data/entries/<科目>.json 是 git 里的权威条目源，
批次条目（如真题派生条目）必须先合并进去，再按 AGENTS 3.3 的流程校验与导入。
合并规则：同 id 或同 point（同科目内）视为重复，跳过并报告；count 自动重算。
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, importer  # noqa: E402


def _load_entries(path: Path) -> list[dict]:
    return importer.load_payload(path).get("entries") or []


def merge_file(entries_dir: Path, subject: str, new_entries: list[dict],
               apply: bool = False) -> dict:
    """把 new_entries 合并进 <entries_dir>/<subject>.json，返回统计。"""
    target = entries_dir / f"{subject}.json"
    if not target.exists():
        raise FileNotFoundError(f"目标条目文件不存在: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    existing = payload.get("entries") or []
    ids = {e.get("id") for e in existing}
    points = {e.get("point") for e in existing}
    added, dup_ids, dup_points = [], [], []
    for entry in new_entries:
        if entry.get("subject") != subject:
            raise ValueError(f"{target.name} 收到其他科目条目: {entry.get('subject')}")
        if entry.get("id") in ids:
            dup_ids.append(entry.get("id"))
            continue
        if entry.get("point") in points:
            dup_points.append(entry.get("point"))
            continue
        added.append(entry)
        ids.add(entry.get("id"))
        points.add(entry.get("point"))
    if added and apply:
        payload["entries"] = existing + added
        payload["count"] = len(payload["entries"])
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return {"subject": subject, "target": str(target), "added": len(added),
            "dup_ids": dup_ids, "dup_points": dup_points,
            "before": len(existing), "after": len(existing) + len(added)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次条目 → data/entries 合并")
    ap.add_argument("files", nargs="+", help="批次条目 JSON（fakao-entry/1.0）")
    ap.add_argument("--entries-dir", default=str(config.DATA_DIR / "entries"))
    ap.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    args = ap.parse_args(argv)

    entries_dir = Path(args.entries_dir)
    grouped: dict[str, list[dict]] = defaultdict(list)
    try:
        for raw in args.files:
            for entry in _load_entries(Path(raw)):
                grouped[entry.get("subject", "")].append(entry)
    except Exception as exc:  # noqa: BLE001 - CLI 兜底
        print(f"ERROR: 读取批次条目失败: {exc}", file=sys.stderr)
        return 1

    failed = False
    for subject in sorted(grouped):
        try:
            stat = merge_file(entries_dir, subject, grouped[subject], args.apply)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {subject} 合并失败: {exc}", file=sys.stderr)
            failed = True
            continue
        verb = "已写入" if args.apply else "将写入"
        print(f"{subject}: {verb} {stat['added']} 条（{stat['before']} → {stat['after']}）")
        for pid in stat["dup_ids"]:
            print(f"  - 跳过重复 id: {pid}")
        for point in stat["dup_points"]:
            print(f"  - 跳过重复考点: {point}")
    if not args.apply and any(grouped):
        print("\n（dry-run，未写入；确认无误后加 --apply）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
