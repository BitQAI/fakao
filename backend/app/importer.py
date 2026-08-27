"""fakao-entry/1.0 侧车 JSON 校验与入库。

规则以 spec 第六节为蓝本裁剪：硬错误整批拒绝，软警告仅记录。
"""
import json
import re
from pathlib import Path

from app import config

SCHEMA_NAME = "fakao-entry/1.0"
PRIORITIES = {"★", "●", "○"}
KNOWN_TAGS = {"新法", "对比", "数字", "计算", "观点展示", "口诀"}
MAX_TAGS = 3
CASE_SOURCES = ("人民法院案例库", "司法部案例库", "最高检指导性案例", "最高法指导性案例")
MAX_CASES = 3
MAX_CASE_REFS = 3
ID_PATTERN = re.compile(r"^(MF|XF|XS|MS|SJ|LL|SG|XZ)-\d{3}$")
ANCHOR_MIN, ANCHOR_MAX = 16, 36
CONCLUSION_MAX = 60
TTS_TEXT_MAX = 150
REQUIRED_KEYS = ("id", "subject", "submodule", "point", "anchor", "conclusion",
                 "priority", "rationale", "sources", "statutes", "tts_text")

INSERT_SQL = """
INSERT OR REPLACE INTO entries
 (id, subject, submodule, point, anchor, conclusion, priority, tags,
  rationale, sources, cases, statutes, note, tts_text, status)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

_REF_CACHE: dict[str, bool] = {}
_CASE_LOC_CACHE: dict[tuple[str, str], bool] = {}


def _find_ref(ref: str) -> bool:
    """ref 是文件名，在 data/ 树中递归匹配；结果缓存避免重复扫描。"""
    if ref in _REF_CACHE:
        return _REF_CACHE[ref]
    found = False
    if config.SOURCE_DIR.exists():
        found = any(config.SOURCE_DIR.glob(f"**/{ref}"))
    _REF_CACHE[ref] = found
    return found


def _case_loc_exists(source: str, loc: str) -> bool:
    key = (source, loc)
    if key in _CASE_LOC_CACHE:
        return _CASE_LOC_CACHE[key]
    found = False
    if config.CASES_INDEX.exists():
        text = config.CASES_INDEX.read_text(encoding="utf-8-sig")
        header = text.splitlines()[0]
        if header.startswith("定位符"):
            found = any(
                line.startswith(f"{loc},") and f",{source}," in line
                for line in text.splitlines()[1:]
            )
    _CASE_LOC_CACHE[key] = found
    return found


def count_case_refs(entries: list[dict]) -> dict[tuple[str, str], int]:
    """统计一批条目中各案例 (source, loc) 被引用的次数。"""
    counts: dict[tuple[str, str], int] = {}
    for e in entries:
        for c in e.get("cases") or []:
            if isinstance(c, dict) and c.get("source") and c.get("loc"):
                key = (c["source"], c["loc"])
                counts[key] = counts.get(key, 0) + 1
    return counts


def _validate_cases(e: dict, tag: str) -> list[str]:
    errs = []
    cases = e.get("cases") or []
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        errs.append(f"{tag} 案例字段非法（需为数组且 ≤{MAX_CASES} 条）")
        return errs
    for c in cases:
        if not isinstance(c, dict) or set(c) != {"source", "loc"}:
            errs.append(f"{tag} 案例元素需恰好含 source/loc: {c!r}")
            continue
        if c["source"] not in CASE_SOURCES:
            errs.append(f"{tag} 案例来源枚举非法: {c['source']!r}")
        if not _case_loc_exists(c["source"], c["loc"]):
            errs.append(f"{tag} 案例不存在于统一索引: {c['source']}#{c['loc']}")
    return errs


def load_payload(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8-sig")
    payload = json.loads(text)
    if payload.get("schema") != SCHEMA_NAME:
        raise ValueError(f"schema 不符: {payload.get('schema')!r}（期望 {SCHEMA_NAME}）")
    return payload


def _row(e: dict, status: str) -> tuple:
    return (e["id"], e["subject"], e["submodule"], e["point"], e["anchor"],
            e["conclusion"], e["priority"], json.dumps(e.get("tags") or [], ensure_ascii=False),
            e["rationale"], json.dumps(e.get("sources") or [], ensure_ascii=False),
            json.dumps(e.get("cases") or [], ensure_ascii=False),
            json.dumps(e.get("statutes") or [], ensure_ascii=False),
            e.get("note"), e.get("tts_text") or "", status)


def validate_entry(e: dict, index: int) -> list[str]:
    errs = []
    tag = f"#{index} {e.get('id', '')}"
    errs.extend(_validate_cases(e, tag))
    for key in REQUIRED_KEYS:
        value = e.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            errs.append(f"{tag} 缺少必填字段 {key}")
    if not ID_PATTERN.fullmatch(str(e.get("id", ""))):
        errs.append(f"{tag} ID 格式错误: {e.get('id')!r}")
    if e.get("priority") not in PRIORITIES:
        errs.append(f"{tag} 优先级非法: {e.get('priority')!r}")
    anchor = e.get("anchor") or ""
    if not (ANCHOR_MIN <= len(anchor) <= ANCHOR_MAX):
        errs.append(f"{tag} 锚点句长度 {len(anchor)} 不在 {ANCHOR_MIN}-{ANCHOR_MAX} 内")
    conclusion = e.get("conclusion") or ""
    if len(conclusion) > CONCLUSION_MAX or not conclusion.endswith("。"):
        errs.append(f"{tag} 结论句超长或未以句号结尾")
    tags = e.get("tags") or []
    if not isinstance(tags, list) or not set(tags) <= KNOWN_TAGS or len(tags) > MAX_TAGS:
        errs.append(f"{tag} 标签非法: {tags!r}")
    sources = e.get("sources") or []
    if not isinstance(sources, list) or not sources:
        errs.append(f"{tag} 参考来源至少 1 条")
    for s in sources:
        if not isinstance(s, dict) or not {"type", "ref", "loc"} <= set(s):
            errs.append(f"{tag} 来源格式非法: {s!r}")
    tts = e.get("tts_text") or ""
    if len(tts) > TTS_TEXT_MAX:
        errs.append(f"{tag} TTS 文本超 {TTS_TEXT_MAX} 字")
    return errs


def import_payload(conn, payload: dict) -> dict:
    entries = payload.get("entries", [])
    errors = []
    warnings = []
    db_rows = conn.execute("SELECT cases FROM entries").fetchall()
    db_usage = count_case_refs(
        [{"cases": json.loads(r["cases"] or "[]")} for r in db_rows]
    )
    batch_usage = count_case_refs(entries)
    for i, e in enumerate(entries):
        errors.extend(validate_entry(e, i))
        for s in e.get("sources") or []:
            ref = s.get("ref", "")
            if ref and not _find_ref(ref):
                warnings.append(f"#{i} {e.get('id', '')} 来源文件不存在: {ref}")
        for c in e.get("cases") or []:
            if isinstance(c, dict) and c.get("source") and c.get("loc"):
                key = (c["source"], c["loc"])
                total = db_usage.get(key, 0) + batch_usage.get(key, 0)
                if total > MAX_CASE_REFS:
                    warnings.append(
                        f"#{i} {e.get('id', '')} 案例引用已达 {total} 次"
                        f"（上限 {MAX_CASE_REFS}）: {c['source']}#{c['loc']}"
                    )
    if errors:
        return {"imported": 0, "errors": errors, "warnings": warnings}
    status = payload.get("status", "draft")
    conn.executemany(INSERT_SQL, [_row(e, status) for e in entries])
    conn.commit()
    return {"imported": len(entries), "errors": [], "warnings": warnings}


def import_file(conn, path: Path) -> dict:
    return import_payload(conn, load_payload(path))
