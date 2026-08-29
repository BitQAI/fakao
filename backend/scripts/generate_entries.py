"""用 DeepSeek 按科目资料批量提炼法考条目（输出 draft JSON）。

用法：
    python scripts/generate_entries.py --subject 刑诉 --target 150
    python scripts/generate_entries.py --subject 刑法 --target 150   # 补量（合并已有）
    python scripts/generate_entries.py --subject 民诉 --dry-run      # 只看资料块统计

流程：读 data/科目资料/<subject>/*.md 按标题切块 → 每批交给 DeepSeek 提炼
→ 校验（字段/长度/来源摘录原文命中/法条可解析）→ 分配 ID → 写 data/entries/<subject>.json。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, config, importer, statutes  # noqa: E402

SUBJECT_PREFIX = {
    "刑法": "XF", "民法": "MF", "刑诉": "XS", "民诉": "MS",
    "商经知": "SJ", "理论法": "LL", "三国法": "SG",
}
_BLOCK_RE = re.compile(r"(?m)(^#{2,4} |^## 【)")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")

SYSTEM_PROMPT = (
    "你是法考客观题冲刺资料提炼助手。根据备考资料提炼客观题条目，"
    "结论必须忠实于资料与现行法，不编造。"
)


def split_blocks(text: str) -> list[str]:
    """按 ### / ## 标题（含【易错点N】）切块，保留标题行。"""
    parts = _BLOCK_RE.split(text)
    blocks = []
    for i in range(1, len(parts) - 1, 2):
        block = parts[i] + (parts[i + 1] or "")
        if len(block) > 20:
            blocks.append(block)
    return blocks


def parse_entries(text: str) -> list[dict] | None:
    """解析 LLM 返回的 JSON 数组；失败返回 None。"""
    if not text:
        return None
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, list) else None


def entry_errors(e: dict) -> list[str]:
    """importer 硬校验 + 来源摘录原文命中（法条解析失败仅软警告，不丢弃）。"""
    errs = importer.validate_entry(e, 0)
    for s in e.get("sources") or []:
        ref, loc = s.get("ref", ""), s.get("loc", "")
        if ref and loc and not importer._loc_exists(ref, loc):
            errs.append(f"来源摘录不存在: {ref}#{loc[:20]}")
    return errs


def next_id(existing: list[str], prefix: str) -> str:
    nums = [int(x.split("-")[1]) for x in existing if x.startswith(prefix + "-")]
    return f"{prefix}-{max(nums, default=0) + 1:03d}"


def _norm(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum())


def fix_loc(ref: str, loc: str) -> str | None:
    """把 LLM 摘录归一化后在原文中定位，回填原文精确连续子串（整句范围）。"""
    nloc = _norm(loc)
    if not nloc:
        return None
    for p in config.SOURCE_DIR.glob(f"**/{ref}"):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8-sig")
        mapping = [i for i, ch in enumerate(text) if ch.isalnum()]
        ntext = "".join(text[i] for i in mapping)
        start = ntext.find(nloc)
        if start == -1:
            start = ntext.find(nloc[:12])
        if start == -1:
            continue
        raw_start = mapping[start]
        raw_end = mapping[start + len(nloc) - 1] + 1
        for i in range(raw_start - 1, -1, -1):
            if text[i] in "。\n":
                raw_start = i + 1
                break
        for i in range(raw_end, len(text)):
            if text[i] in "。\n":
                raw_end = i + 1
                break
        return text[raw_start:raw_end][:80]
    return None


def fix_anchor(a: str) -> str:
    a = a.strip()
    if len(a) <= 36:
        return a
    cut = a[:34]
    idx = max(cut.rfind("，"), cut.rfind("；"), cut.rfind("、"))
    if idx >= 20:
        cut = cut[:idx]
    return cut


def fix_rationale(r: str, priority: str = "普通") -> str:
    r = (r or "").strip()
    if r:
        return r
    return {
        "高频考点": "高频考点，常考细节。",
        "易错陷阱": "易错陷阱，注意区分。",
        "新增必考": "新增必考，近年新增。",
        "普通": "普通考点，了解即可。",
    }.get(priority, "普通考点，了解即可。")


def fix_conclusion(c: str) -> str:
    c = c.strip()
    if not c:
        return "结论正确。"
    if len(c) > 59:
        c = c[:59]
        idx = c.rfind("。")
        if idx >= 20:
            c = c[:idx + 1]
    if not c.endswith("。"):
        c = c.rstrip("，；、 ") + "。"
    return c


def fix_tts(t: str) -> str:
    return t.strip()[:150]


def _build_prompt(chunk: list[tuple[str, str]]) -> str:
    parts = [f"--- 资料文件 {ref} ---\n{block}" for ref, block in chunk]
    return (
        "根据下列法考备考资料提炼客观题条目（每条 anchor 场景不同，point 不重复）。\n"
        "只输出 JSON 数组，元素字段：submodule/point/anchor/conclusion/priority/"
        "rationale/sources/statutes/note/tts_text。约束：\n"
        "- submodule：所属子科目（如 基本原则/分则-财产犯罪）\n"
        "- point ≤ 15 字；anchor 16-36 字（客观题题干场景）\n"
        "- conclusion ≤ 60 字且以句号结尾，涉及法条时注明条号\n"
        "- priority ∈ 高频考点/易错陷阱/新增必考/普通\n"
        "- sources 至少 1 条：{\"type\":\"高频\",\"ref\":\"资料文件名\",\"loc\":\"原文连续子串，必须逐字照抄资料\"}\n"
        "- statutes 为条文数组（如 [\"刑诉法16条\"]），资料未提则 []\n"
        "- note 为易错提示或 null\n"
        "- tts_text ≤ 150 字，格式【科目·考点】场景。结论。\n"
        "不要输出 Markdown 或任何 JSON 之外的内容。\n\n" + "\n\n".join(parts)
    )


def generate(subject: str, target: int = 0, batch: int = 5,
             out_path: Path | None = None, retries: int = 2) -> dict:
    subject_dir = config.DATA_DIR / "科目资料" / subject
    out_path = Path(out_path) if out_path else config.DATA_DIR / "entries" / f"{subject}.json"
    prefix = SUBJECT_PREFIX[subject]

    blocks: list[tuple[str, str]] = []
    for md in sorted(subject_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8-sig")
        blocks.extend((md.name, b) for b in split_blocks(text))

    existing: list[dict] = []
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8")).get("entries", [])
    existing_ids = [e["id"] for e in existing]
    known_points = {e["point"] for e in existing}

    stats = {"ok": 0, "fail": 0, "discard": 0, "blocks": len(blocks)}
    counter = max([int(x.split("-")[1]) for x in existing_ids
                   if x.startswith(prefix + "-")], default=0)
    new_entries: list[dict] = []
    used_points = set(known_points)

    for i in range(0, len(blocks), batch):
        if target and stats["ok"] >= target:
            break
        chunk = blocks[i:i + batch]
        user = _build_prompt(chunk)
        parsed = None
        for _ in range(retries + 1):
            raw = ai.call_llm(SYSTEM_PROMPT, user, temperature=0.4, max_tokens=5000)
            parsed = parse_entries(raw)
            if parsed is not None:
                break
        if parsed is None:
            stats["fail"] += 1
            print(f"[{i // batch + 1}] FAIL 批次 {i + 1}-{i + len(chunk)}（输出不可解析）")
            continue
        for e in parsed:
            if e.get("point") in used_points:
                stats["discard"] += 1
                continue
            counter += 1
            e["id"] = f"{prefix}-{counter:03d}"
            e["subject"] = subject
            e["anchor"] = fix_anchor(e.get("anchor", ""))
            e["rationale"] = fix_rationale(e.get("rationale", ""), e.get("priority", ""))
            fixed_sources = []
            for s in e.get("sources") or []:
                fixed = fix_loc(s.get("ref", ""), s.get("loc", ""))
                fixed_sources.append({**s, "loc": fixed} if fixed else s)
            e["sources"] = fixed_sources
            e["conclusion"] = fix_conclusion(e.get("conclusion", ""))
            e["tts_text"] = fix_tts(e.get("tts_text", ""))
            for st in e.get("statutes") or []:
                if st and statutes.resolve_statute(st) is None:
                    stats["warn"] = stats.get("warn", 0) + 1
            errs = entry_errors(e)
            if errs:
                stats["discard"] += 1
                print(f"  丢弃 {e.get('id')} {e.get('point')}: {errs[0][:80]}")
                continue
            used_points.add(e["point"])
            new_entries.append(e)
            stats["ok"] += 1

    if new_entries:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "fakao-entry/1.0",
            "source_md": str(subject_dir),
            "status": "draft",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(existing) + len(new_entries),
            "entries": existing + new_entries,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"OK: {subject} 新增 {len(new_entries)} 条 -> {out_path}")
    else:
        print(f"WARN: {subject} 无新增条目（资料块 {len(blocks)}，"
              f"失败批次 {stats['fail']}）")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按科目资料批量生成法考条目 draft")
    ap.add_argument("--subject", required=True, help="科目名（刑法/民法/刑诉/民诉/商经知/理论法/三国法）")
    ap.add_argument("--target", type=int, default=0, help="目标新增条数（0=跑完所有资料块）")
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--out", default=None, help="输出 JSON 路径")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.subject not in SUBJECT_PREFIX:
        print(f"未知科目: {args.subject}", file=sys.stderr)
        return 2
    if args.dry_run:
        subject_dir = config.DATA_DIR / "科目资料" / args.subject
        for md in sorted(subject_dir.glob("*.md")):
            blocks = split_blocks(md.read_text(encoding="utf-8-sig"))
            print(f"{md.name}: {len(blocks)} 块")
        return 0
    stats = generate(args.subject, target=args.target, batch=args.batch, out_path=args.out)
    print(f"汇总: {stats}")
    return 1 if stats["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
