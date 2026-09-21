"""把投递的法律原文归一成 data/法条库 的标准格式。

背景：官方站全文托管在内网 OSS，公网取不到（详见 fetch_statutes.py 的说明），
因此正文由人工投递到 data/法条库/_inbox/，本脚本负责切条、统一写法、校验、
并合成标准文件头（元信息来自 fetch_statutes.py 产出的 _meta.json）。

投递格式：随便什么纯文本都行（docx 请先转 txt/md）。脚本会
  · 保留  第X编 / 第X章 / 第X节  标题行
  · 保留  第X条 正文（多段合并到同一条）
  · 统一为「第十条　正文」写法（阿拉伯数字条号转中文）
  · 丢弃目录、页眉页脚、颁布说明等非条文行

用法：
    python scripts/normalize_statutes.py --dry-run          # 只看会生成什么
    python scripts/normalize_statutes.py                    # 全量归一
    python scripts/normalize_statutes.py --only 商标法
    python scripts/normalize_statutes.py --law 中华人民共和国商标法 --file x.txt
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.statute_index import int2cn  # noqa: E402

INBOX = config.STATUTE_DIR / "_inbox"
META_PATH = config.STATUTE_DIR / "_meta.json"

ARTICLE_RE = re.compile(
    r"^\s*\**\s*第\s*(?P<num>[0-9]+|[零一二三四五六七八九十百千]+)\s*条"
    r"(?P<sub>\s*之\s*[零一二三四五六七八九十]+)?\s*\**\s*[　\s]*(?P<body>.*)$")
HEADING_RE = re.compile(
    r"^\s*(第\s*[零一二三四五六七八九十百千]+\s*[编章节])[　\s]*(.*)$")
#: 「一、管辖」式标题（民诉解释等），限长且不带句号，避免误吃条文正文
NUMBERED_RE = re.compile(r"^([一二三四五六七八九十]{1,3})、[　\s]*(.{1,20})$")
#: 常见的 PDF/网页噪声行（页码、页眉、来源说明）
NOISE_RES = (
    re.compile(r"^[—\-–\s]*第?\s*\d+\s*页?[—\-–\s]*$"),
    re.compile(r"^[—\-–]{2,}\s*\d+\s*[—\-–]{2,}$"),
    re.compile(r"^(来源|网址|责任编辑|扫一扫|上一篇|下一篇)[:：]"),
    re.compile(r"^目\s*录$"),
)


def _cn2int(s: str) -> int | None:
    from app.statutes import _cn2int as conv
    return conv(s)


def normalize_text(raw: str) -> tuple[list[str], list[str]]:
    """→ (正文行, 问题列表)。保留条文章节，丢弃噪声。"""
    items: list[tuple[str, str]] = []   # ("heading" | "article", 文本)
    problems: list[str] = []
    seen: list[int] = []
    cur: int | None = None
    for raw_line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        # 只去首尾空白，不动正文内部的全角空格（如「总　　则」的间距）
        line = raw_line.strip()
        if not line:
            continue
        if any(rx.match(line) for rx in NOISE_RES):
            continue
        m = ARTICLE_RE.match(line)
        if m:
            num = _cn2int(m.group("num"))
            if num is None:
                problems.append(f"无法解析条号：{line[:24]}")
                continue
            sub = m.group("sub") or ""
            sub = sub.replace(" ", "")
            label = f"第{int2cn(num)}条{sub}"
            body = m.group("body").strip()
            if seen and not sub and num <= seen[-1]:
                problems.append(f"条号未递增：{label}（前一条 {int2cn(seen[-1])}）")
            if not sub:
                seen.append(num)
            items.append(("article", f"{label}\u3000{body}".rstrip("\u3000")))
            cur = len(items) - 1
            continue
        if HEADING_RE.match(line) or (not line.endswith("。")
                                      and NUMBERED_RE.match(line)):
            items.append(("heading", line))
            cur = None
            continue
        if cur is not None and items[cur][0] == "article":
            items[cur] = ("article", items[cur][1] + "\n" + line)

    # 去目录：若首个标题在后面原样再次出现、且中间没有条文，则该段是目录
    if items and items[0][0] == "heading":
        for i in range(1, len(items)):
            if any(k == "article" for k, _ in items[:i]):
                break
            if items[i] == items[0]:
                del items[:i]
                break
    return [text for _, text in items], problems


def build_header(law: str, meta: dict | None) -> list[str]:
    head = [f"# {law}", ""]
    if meta and meta.get("found"):
        bits = [f"公布日期：{meta.get('公布日期', '')}",
                f"施行日期：{meta.get('施行日期', '')}",
                f"效力状态：{meta.get('效力状态', '')}",
                f"制定机关：{meta.get('制定机关', '')}"]
        head.append("- " + "  ".join(bits))
        head.append(f"- 来源：国家法律法规数据库 flk.npc.gov.cn "
                    f"(bbbs={meta.get('bbbs', '')})")
        if meta.get("其他版本"):
            older = "；".join(
                f"{v.get('公布日期')}公布/{v.get('施行日期')}施行"
                for v in meta["其他版本"][:3])
            head.append(f"- 历史版本：{older}")
    else:
        head.append("- 来源：人工投递（_meta.json 中无对应元信息，需补登）")
    head += ["", law, ""]
    return head


def load_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8")).get("items", {})


def _match_meta(meta: dict, law: str, stem: str) -> dict | None:
    for key in (law, stem):
        if key in meta:
            return meta[key]
    short = law.replace("中华人民共和国", "")
    for key, val in meta.items():
        if val.get("found") and (key == short or short in key or key in law):
            return val
    return None


def normalize_one(path: Path, law: str, meta: dict, force: bool,
                  dry_run: bool) -> str:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    body, problems = normalize_text(raw)
    if not body:
        return f"跳过（未解析出任何条文）：{path.name}"
    target = config.STATUTE_DIR / f"{law}.md"
    if target.exists() and not force and not dry_run:
        return f"跳过（已存在，用 --force 覆盖）：{target.name}"
    matched = _match_meta(meta, law, path.stem)
    content = "\n".join(build_header(law, matched) + body) + "\n"
    articles = sum(1 for l in body if l.startswith("第") and "条" in l[:12])
    if dry_run:
        note = f"；问题 {len(problems)} 处" if problems else ""
        return f"[dry-run] {path.name} → {target.name}：{articles} 条{note}"
    target.write_text(content, encoding="utf-8")
    return (f"生成 {target.name}：{articles} 条"
            + (f"，问题 {len(problems)} 处：{problems[:2]}" if problems else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="归一投递的法条原文")
    ap.add_argument("--only", help="只处理文件名或法名包含该词的项")
    ap.add_argument("--law", help="显式指定法名（配合 --file 单文件处理）")
    ap.add_argument("--file", help="单文件路径（相对仓库或绝对路径）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的法条文件")
    args = ap.parse_args()

    meta = load_meta()
    if args.file:
        path = Path(args.file)
        law = args.law or path.stem
        print(normalize_one(path, law, meta, args.force, args.dry_run))
        return 0

    if not INBOX.exists():
        print(f"投递目录不存在：{INBOX}\n把法律原文（txt/md）放进去再跑一次。")
        return 1
    files = sorted(p for p in INBOX.iterdir()
                   if p.suffix.lower() in (".txt", ".md") and not p.name.startswith("."))
    if args.only:
        files = [p for p in files if args.only in p.name]
    if not files:
        print(f"{INBOX} 下没有待处理的 .txt/.md 文件。")
        return 1
    for path in files:
        law = args.law or path.stem
        print(normalize_one(path, law, meta, args.force, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
