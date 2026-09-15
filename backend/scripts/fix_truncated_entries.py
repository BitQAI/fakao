"""补全历史上被 fix_* 硬切损坏的条目字段（conclusion / tts_text / anchor）。

用法：
    python scripts/fix_truncated_entries.py --dry-run                 # 只列受损清单
    python scripts/fix_truncated_entries.py --only=conclusion,tts     # 实际写回
    python scripts/fix_truncated_entries.py --subject 三国法 --batch 10
    python scripts/fix_truncated_entries.py --with-anchor             # 纳入 anchor 候选

流程：扫描 data/entries/*.json → 启发式挑出受损字段 → 按批交 DeepSeek 补全
→ 自检（法条号完整/括号配对/无 Markdown/不短于原文）→ 写回 JSON。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, config, statutes  # noqa: E402

ENTRY_FIELDS = ("conclusion", "tts_text", "anchor")
CUT_CITE = re.compile(r"第[\d一二三四五六七八九十百千万]+。\s*$")
MARKDOWN = re.compile(r"[`*#]")
CITATION = re.compile(r"(《[^》]{1,20}》|[^\s，。；、（）()《》第]{2,12}?)"
                      r"第[\d一二三四五六七八九十百千万]+条(?:之[\d一二三四五六七八九十]+)?")
PAIRS = (("（", "）"), ("《", "》"), ("“", "”"), ("(", ")"))
CONCLUSION_NEAR = 58   # 结论接近 60 字硬上限，末句可能被切
TTS_NEAR = 148         # TTS 接近 150 字硬上限
ANCHOR_NEAR = 34       # fix_anchor 曾按 34 字切

SYSTEM_PROMPT = (
    "你是法考条目数据修复助手。历史处理中部分字段被按字符数硬截断，"
    "可能断在词中、括号中或法条号中间。只做补全，不改写、不新增原文没有的结论。"
)


def unbalanced(text: str) -> str | None:
    """检查成对符号是否闭合，返回不配对的描述。"""
    for left, right in PAIRS:
        if text.count(left) != text.count(right):
            return f"{left}{right} 不配对"
    return None


def damage_reason(entry: dict, field: str) -> str | None:
    """启发式判断字段是否被截断；返回原因，未受损返回 None。"""
    text = (entry.get(field) or "").strip()
    if not text:
        return None
    bad = unbalanced(text)
    if bad:
        return bad
    if field == "conclusion":
        if CUT_CITE.search(text):
            return "法条号被切成「第N。」"
        if len(text) >= CONCLUSION_NEAR and not text.endswith("。"):
            return "接近 60 字上限且末句中断"
    elif field == "tts_text":
        if len(text) >= TTS_NEAR:
            return "接近 150 字上限"
    elif field == "anchor" and len(text) >= ANCHOR_NEAR:
        return "长度达 fix_anchor 截断线，需复核是否断词"
    return None


def scan_damaged(entries: list[dict], fields: tuple[str, ...] = ENTRY_FIELDS):
    """返回 [(条目索引, 条目, 字段, 原因)]。"""
    hits = []
    for i, e in enumerate(entries):
        for field in fields:
            reason = damage_reason(e, field)
            if reason:
                hits.append((i, e, field, reason))
    return hits


def _grams(text: str, n: int = 2) -> set[str]:
    t = re.sub(r"[^\u4e00-\u9fff]", "", text)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def _law_of(statute: str) -> str:
    """从「民诉法第275条」取「民诉法」。"""
    return re.split(r"第?[\d一二三四五六七八九十百千万]+条", statute)[0].strip("《》 ")


def _article_blocks(path: Path) -> dict[str, str]:
    """按「第N条」切法条库文件，含条文下的款项（parse_law_file 不含款项）。"""
    blocks: dict[str, str] = {}
    current, buf = None, []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"^\**第([零一二三四五六七八九十百千]+)条", line.strip())
        if m:
            if current:
                blocks[current] = "\n".join(buf)
            current, buf = m.group(1), [line]
        elif current:
            buf.append(line)
    if current:
        blocks[current] = "\n".join(buf)
    return blocks


def statute_hints(e: dict, top: int = 3) -> list[dict]:
    """按词面重合度从法条库挑最相关条文，供模型核对条号。"""
    context = "".join(str(e.get(k) or "") for k in
                      ("point", "anchor", "conclusion"))
    grams = _grams(context)
    hints = []
    for st in e.get("statutes") or []:
        law = _law_of(st)
        path = statutes.resolve_law_file(law)
        if path is None:
            continue
        scored = []
        for num, body in _article_blocks(path).items():
            body_grams = _grams(body)
            if not body_grams:
                continue
            score = len(grams & body_grams) / (len(body_grams) ** 0.5)
            if score:
                scored.append((round(score, 3), num, re.sub(r"\s+", "", body)))
        scored.sort(reverse=True)
        cited = statutes.resolve_statute(st)
        for score, num, body in scored[:top]:
            hints.append({"law": law, "cited": st, "article": f"{law}第{num}条",
                          "body": body[:140], "score": score,
                          "is_cited": f"{law}第{num}条" == st.replace(" ", "")})
        if cited:
            hints.append({"law": law, "cited": st, "article": f"（当前引用）{st}",
                          "body": re.sub(r"\s+", "", cited)[:140], "score": 0,
                          "is_cited": True})
    return hints


def _repair_item(e: dict, field: str, reason: str) -> dict:
    return {
        "id": e.get("id"), "field": field, "reason": reason,
        "point": e.get("point"), "anchor": e.get("anchor"),
        "current": e.get(field),
        "statutes": e.get("statutes") or [],
        "statute_hints": statute_hints(e),
        "sources": [{"ref": s.get("ref"), "loc": s.get("loc")}
                    for s in (e.get("sources") or [])],
    }


def build_prompt(items: list[dict]) -> str:
    return (
        "下列法考条目的指定字段可能被字符截断（断在词中/括号中/法条号中间）。逐条判断：\n"
        "- 确实被截断：只补全被切掉的部分，不得新增原文没有的结论或法条；"
        "法条号补全为「第N条」；括号闭合；结论仍以句号结尾\n"
        "- 内容本身完整：返回 null，不要改写\n"
        "- field=tts_text 且确有法条适用时，补全后改为法条先行："
        "「依照刑诉法第192条、第193条规定，……构成XX罪。」；无明确法条适用则保持原结构\n"
        "- tts_text 是朗读文本，禁止 Markdown 标记（反引号/星号/井号）\n"
        "- sources 的 loc 是资料原文摘录，可作为补全依据，不得超出其含义\n"
        "- statute_hints 是法条库原文片段（含条号）。若结论引用的条号与条文内容不符，"
        "以 hints 中内容匹配的条号为准；无法确定正确条号时，删除具体条号，"
        "改写为「依据<法名>关于<要点>的规定」，不得保留错误条号\n"
        "只输出 JSON 数组，元素形如 {\"id\":\"SG-067\",\"field\":\"conclusion\","
        "\"text\":\"补全后的完整文本\"}；未截断的项 text 为 null。\n\n"
        "输入：\n" + json.dumps(items, ensure_ascii=False, indent=1)
    )


def parse_repairs(text: str) -> list[dict] | None:
    """解析模型返回的修复数组。"""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, list) else None


def check_repair(field: str, old: str, new: str) -> str | None:
    """修复结果自检；通过返回 None，否则返回拒绝原因。"""
    new = (new or "").strip()
    if not new:
        return "空结果"
    if len(new) < len(old):
        return f"比原文更短（{len(old)} -> {len(new)}）"
    bad = unbalanced(new)
    if bad:
        return f"修复后仍{bad}"
    if field == "conclusion":
        if CUT_CITE.search(new):
            return "法条号仍不完整"
        if not new.endswith("。"):
            return "未以句号结尾"
    if field == "tts_text" and MARKDOWN.search(new):
        return "含 Markdown 标记"
    return citation_problem(new)


def citation_problem(text: str) -> str | None:
    """条号自检：法条库收录该法时按条号核验，未收录则放行并标注 UNVERIFIED。"""
    for m in CITATION.finditer(text):
        cite = re.sub(r"^(依照|依据|根据|按照|按|本|该|上述)+", "",
                      m.group(0).strip("《》"))
        law = re.sub(r"^\d{4}年(度)?", "", _law_of(cite)).strip("《》〈〉 ")
        if statutes.resolve_law_file(law) is None:
            print(f"  UNVERIFIED 法条库未收录：{cite}")
            continue
        if statutes.resolve_statute(cite) is None:
            return f"条号不存在：{cite}"
    return None


def repair_batch(items: list[dict], retries: int = 2) -> dict[tuple[str, str], str]:
    """调用模型补全一批字段，返回 {(id, field): 新文本}。"""
    out: dict[tuple[str, str], str] = {}
    if not items:
        return out
    prompt = build_prompt(items)
    parsed = None
    for _ in range(retries + 1):
        parsed = parse_repairs(ai.call_llm(SYSTEM_PROMPT, prompt,
                                           temperature=0.2, max_tokens=4000))
        if parsed is not None:
            break
    if parsed is None:
        print("  FAIL 批次输出不可解析，跳过")
        return out
    by_key = {(i["id"], i["field"]): i for i in items}
    for r in parsed:
        key = (r.get("id"), r.get("field"))
        src = by_key.get(key)
        if src is None or not r.get("text"):
            continue
        reason = check_repair(key[1], src["current"] or "", r["text"])
        if reason:
            print(f"  REJECT {key[0]}.{key[1]}: {reason}")
            continue
        out[key] = r["text"].strip()
    return out


def collect_targets(subject: str | None, fields: tuple[str, ...],
                    only_id: str | None):
    """读取 entries JSON，返回 [(路径, 条目列表, 受损清单)]。"""
    targets = []
    for path in sorted((config.DATA_DIR / "entries").glob("*.json")):
        if subject and path.stem != subject:
            continue
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
        hits = [h for h in scan_damaged(entries, fields)
                if not only_id or h[1].get("id") == only_id]
        if hits:
            targets.append((path, entries, hits))
    return targets


def write_back(path: Path, entries: list[dict]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"] = entries
    payload["count"] = len(entries)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(path: Path, entries: list[dict], hits, batch: int, dry_run: bool) -> int:
    """处理单个条目文件，返回实际修复条数。"""
    print(f"\n== {path.name}：受损 {len(hits)} 处 ==")
    for i, e, field, reason in hits:
        print(f"  - {e.get('id')} {field}（{reason}）")
    if dry_run:
        return 0
    fixed = 0
    for start in range(0, len(hits), batch):
        chunk = hits[start:start + batch]
        items = [_repair_item(e, field, reason) for _, e, field, reason in chunk]
        repairs = repair_batch(items)
        for i, e, field, _ in chunk:
            new = repairs.get((e.get("id"), field))
            if not new or new == (e.get(field) or "").strip():
                continue
            print(f"  FIX {e.get('id')}.{field}\n"
                  f"    旧: {(e.get(field) or '')[:80]}\n"
                  f"    新: {new[:80]}")
            entries[i][field] = new
            fixed += 1
    if fixed:
        write_back(path, entries)
        print(f"  已写回 {path}（{fixed} 处）")
    return fixed


def main() -> None:
    ap = argparse.ArgumentParser(description="补全被硬切损坏的条目字段")
    ap.add_argument("--only", default="conclusion,tts",
                    help="逗号分隔：conclusion,tts,anchor（tts 指 tts_text）")
    ap.add_argument("--with-anchor", action="store_true", help="纳入 anchor 候选")
    ap.add_argument("--subject", help="只处理该科目 JSON")
    ap.add_argument("--id", dest="only_id", help="只处理该条目 ID")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 处（0=不限）")
    ap.add_argument("--dry-run", action="store_true", help="只列清单不写回")
    args = ap.parse_args()

    names = [x.strip() for x in args.only.split(",") if x.strip()]
    fields = []
    for n in names:
        field = "tts_text" if n == "tts" else n
        if field not in ENTRY_FIELDS:
            raise SystemExit(f"未知字段: {n}")
        fields.append(field)
    if args.with_anchor and "anchor" not in fields:
        fields.append("anchor")

    total = 0
    for path, entries, hits in collect_targets(args.subject, tuple(fields),
                                               args.only_id):
        if args.limit:
            hits = hits[:args.limit]
        total += run(path, entries, hits, args.batch, args.dry_run)
    print(f"\n完成：修复 {total} 处"
          f"{'（dry-run，未写回）' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
