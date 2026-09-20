"""题库版本库资产：`quizzes` 表 ⇄ `data/quiz_bank/*.json`。

与 `app/quiz_bank.py` 分工：那边管运行时读写与抽题，这边只管序列化与文件布局，
供 `scripts/export_quiz_bank.py` / `scripts/import_quiz_bank.py` 调用。

文件按「origin + 科目」切分（与 `data/entries/*.json` 同思路），
每题一行（紧凑、diff 友好），空字段不落盘。
"""
import json
from datetime import date
from pathlib import Path

from app import quiz_bank

SCHEMA = "fakao-quiz-bank/1.0"

#: 导出字段（空值不落盘，控制文件体积）
_FIELDS = ("entry_id", "qtype", "point", "stem", "options", "answer",
           "analysis", "basis", "variant")


def file_name(origin: str, subject: str) -> str:
    """题库文件名：`<origin>-<科目>.json`（科目为空时落「未分类」）。"""
    return f"{origin}-{subject or '未分类'}.json"


def _placeholders(values) -> str:
    return ",".join("?" * len(values))


def _sort_key(item: dict) -> tuple:
    return (item["entry_id"], item["basis"], item["stem"])


def read_groups(conn, origins=("bank", "judge"),
                statuses=("published",)) -> list[dict]:
    """按「origin + 科目」分组读出题库题，组内排序稳定。"""
    rows = conn.execute(
        "SELECT entry_id, subject, point, qtype, origin, stem, options, answer,"
        " analysis, basis, variant FROM quizzes"
        f" WHERE origin IN ({_placeholders(origins)})"
        f" AND status IN ({_placeholders(statuses)})"
        " ORDER BY origin, subject, entry_id, basis, stem",
        (*origins, *statuses)).fetchall()
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        item = {"entry_id": r["entry_id"] or "", "qtype": r["qtype"],
                "point": r["point"] or "", "stem": r["stem"],
                "options": json.loads(r["options"] or "[]"),
                "answer": r["answer"], "analysis": r["analysis"] or "",
                "basis": r["basis"] or "", "variant": r["variant"] or ""}
        groups.setdefault((r["origin"], r["subject"] or ""), []).append(item)
    return [{"origin": origin, "subject": subject,
             "items": sorted(items, key=_sort_key)}
            for (origin, subject), items in sorted(groups.items())]


def dumps(origin: str, subject: str, items: list[dict],
          exported_at: str | None = None) -> str:
    """序列化一个题库文件：头信息 + 每题一行。"""
    head = [
        "{",
        f'  "schema": "{SCHEMA}",',
        f'  "origin": {json.dumps(origin, ensure_ascii=False)},',
        f'  "subject": {json.dumps(subject, ensure_ascii=False)},',
        f'  "exported_at": "{exported_at or date.today().isoformat()}",',
        f'  "count": {len(items)},',
        '  "items": [',
    ]
    body = []
    for i, item in enumerate(items):
        payload = {k: item[k] for k in _FIELDS
                   if item.get(k) not in ("", [], None)}
        body.append("    " + json.dumps(payload, ensure_ascii=False)
                    + ("," if i < len(items) - 1 else ""))
    return "\n".join(head + body + ["  ]", "}"]) + "\n"


def export(conn, out_dir: Path, origins=("bank", "judge"),
           statuses=("published",), dry_run: bool = False) -> dict:
    """导出题库到 out_dir；返回 {files, total}（空分组不落盘）。"""
    groups = [g for g in read_groups(conn, origins, statuses) if g["items"]]
    files = []
    for group in groups:
        path = Path(out_dir) / file_name(group["origin"], group["subject"])
        if not dry_run:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            path.write_text(dumps(group["origin"], group["subject"],
                                  group["items"]), encoding="utf-8")
        files.append({"path": path, "origin": group["origin"],
                      "subject": group["subject"], "count": len(group["items"])})
    return {"files": files, "total": sum(f["count"] for f in files)}


def parse(text: str) -> dict:
    """解析题库文件，校验 schema 与必需字段。"""
    data = json.loads(text)
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError("不是题库文件（缺少 items）")
    if data.get("schema") != SCHEMA:
        raise ValueError(f"schema 不匹配：{data.get('schema')!r} != {SCHEMA!r}")
    for item in data["items"]:
        if not item.get("stem") or "answer" not in item:
            raise ValueError(f"题目缺字段：{str(item)[:60]}")
    return data


def import_payload(conn, payload: dict, replace: bool = False) -> dict:
    """把一份题库 payload 幂等写回 quizzes，返回 {written, skipped, orphan}。

    `quizzes.entry_id` 有外键约束：目标库缺该条目（entries 还没导入）时跳过并计入
    `orphan`，避免整批导入中断。
    """
    origin = payload["origin"]
    subject = payload.get("subject", "")
    entry_ids = {r["id"] for r in conn.execute("SELECT id FROM entries")}
    written = skipped = orphan = 0
    for item in payload.get("items", []):
        entry_id = item.get("entry_id") or None
        if entry_id and entry_id not in entry_ids:
            orphan += 1
            continue
        before = conn.total_changes
        quiz_bank.save_question(
            conn, qtype=item.get("qtype") or "choice", origin=origin,
            entry_id=entry_id,
            subject=item.get("subject") or subject, point=item.get("point", ""),
            stem=item["stem"], options=item.get("options") or [],
            answer=item["answer"], analysis=item.get("analysis", ""),
            basis=item.get("basis", ""), variant=item.get("variant", ""),
            status="published", replace=replace)
        if conn.total_changes > before:
            written += 1
        else:
            skipped += 1
    return {"written": written, "skipped": skipped, "orphan": orphan}
