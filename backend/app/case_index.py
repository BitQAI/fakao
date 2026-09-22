"""案例库检索与文书化分节（只读）。

与 app/cases.py 分工：cases.py 负责 JSONL → SQLite 装载与单篇读取；
本模块负责「关键词模糊检索」与「原文 → 文书小节」的展示层解析，
不改表结构、不写回数据库，原文始终保留在 cases.text。
"""
from __future__ import annotations

import json
import re

from app.cases import CASE_SOURCES

#: 独占一行的裸小标题（最高法指导性案例等）
_BARE_HEADERS = (
    "关键词", "裁判要点", "裁判要旨", "相关法条", "相关法律规定", "相关立法",
    "基本案情", "案情简介", "裁判理由", "裁判结果", "要旨", "指导意义",
    "检察机关履职过程", "检察机关履职情况", "检察机关监督情况",
    "指控与证明犯罪", "诉讼过程", "诉讼过程和结果",
)
_BARE_RE = re.compile(r"^(%s)(?:[　\s]+(.*))?$" % "|".join(_BARE_HEADERS))
#: 【小节】式标记（最高检 / 司法部）
_BRACKET_RE = re.compile(r"^【([^】]{1,12})】[　\s]*(.*)$")
#: 丢弃页眉页脚：markdown 标题、批次元信息、编号行
_DROP_RES = (
    re.compile(r"^（发布批次[:：].*）$"),
    re.compile(r"^（[^）]{0,40}讨论通过[^）]{0,40}）$"),
    re.compile(r"^指导性?案例\s*第?\s*\d+\s*号([:：].*)?$"),
    re.compile(r"^（检例第\d+号）$"),
)
_HEADING_RE = re.compile(r"^#+[　\s]*")
_HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_SENT_END = re.compile(r"[。！？；：”』》）\)]$")
_NUMBERED = re.compile(r"^\d+[.、]")
#: 疑似漏进来的下一篇案例标题：纯汉字、无任何标点数字
_TITLE_LINE = re.compile(r"^[\u4e00-\u9fff·]{2,30}$")
#: 这些小节末尾常残留下一篇案例标题，需要清理
_TRIM_TRAILING = {"相关规定", "相关法律规定", "相关立法"}
#: 提到正文最前的小节（阅读顺序优化，内容不改）
_HEAD_LABELS = ("关键词", "裁判要旨", "要旨", "裁判要点")
_LAW_LABELS = ("相关法条", "相关规定", "相关法律规定", "相关立法")
#: 正文末尾抽出来的审理程序，排在最后
_TAIL_LABELS = ("审理程序",)
_SENT_SPLIT = re.compile(r"(?<=[。！？])")
_MIN_DUP_SENT = 15
#: 全角空格≥2 视为正文与「关联索引」侧栏的分隔
_GAP = re.compile(r"[　]{2,}")
_PROC_RE = re.compile(r"^(一审|二审|再审|终审|执行|申诉|复议|原审)[:：]")
_LAW_LINE_RE = re.compile(r"^《[^》]{2,60}》.*?第[0-9零一二三四五六七八九十百千]+条")
_SNIPPET_PAD = 40
#: 命中字段权重：标题 > 案号 > 关键词 > 类别 > 正文
_FIELDS = (("title", 6), ("case_no", 4), ("keywords", 3), ("category", 2), ("text", 1))


def _clean_line(line: str) -> str:
    """去掉 markdown 标题记号；整行是页眉页脚元信息时返回空串。"""
    if _HR_RE.match(line.strip()):
        return ""
    text = _HEADING_RE.sub("", line.strip())
    if not text or all(ch in "#　 " for ch in text):
        return ""
    return "" if any(rx.match(text) for rx in _DROP_RES) else text


def _merge_wrapped(paras: list[str]) -> list[str]:
    """上一段没有句末标点时与下一行拼接（原文存在被换行切碎的段落）。"""
    out: list[str] = []
    for para in paras:
        tail = _GAP.split(out[-1])[-1].strip() if out else ""
        if out and not _SENT_END.search(tail) and not _footer_kind(tail):
            out[-1] += para
        else:
            out.append(para)
    return out


def _split_groups(text: str) -> list[list]:
    """按【X】/ 裸行小标题 / 无标记正文分组，返回 [[label, [line, ...]], ...]。"""
    grouped: list[list] = []  # [label, [line, ...]]
    for raw in (text or "").splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        m = _BRACKET_RE.match(line)
        if m:
            head = m.group(2).strip()
            grouped.append([m.group(1).strip(), [head] if head else []])
            continue
        m = _BARE_RE.match(line)
        if m:
            head = (m.group(2) or "").strip()
            grouped.append([m.group(1), [head] if head else []])
            continue
        if not grouped:
            grouped.append(["", []])
        grouped[-1][1].append(line)
    return grouped


def _lift_summary(section: dict) -> tuple[dict, dict | None]:
    """人民法院案例库：开头的「1. 2. 」编号段实为裁判要旨，单独提出来。"""
    lines = section["text"].splitlines()
    n = 0
    while n < len(lines) and _NUMBERED.match(lines[n]):
        n += 1
    if n == 0 or n == len(lines):
        return section, None
    summary = {"label": "裁判要旨", "text": "\n".join(lines[:n])}
    return {"label": "", "text": "\n".join(lines[n:]).strip()}, summary


def _drop_leaked_tail(grouped: list[list]) -> list[list]:
    """最高检原文末节常残留下一篇案例标题（无标点短句），去掉。"""
    if grouped and grouped[-1][0] in _TRIM_TRAILING:
        lines = grouped[-1][1]
        while len(lines) > 1 and _TITLE_LINE.match(lines[-1]):
            lines.pop()
    return [g for g in grouped if any(line.strip() for line in g[1])]


def _dedupe_sentences(para: str) -> tuple[str, int]:
    """段落内连续重复的句子块只留一份（原文脏数据：整段被判词复制两遍）。"""
    sents = [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]
    kept: list[str] = []
    dropped = 0
    i = 0
    while i < len(sents):
        run = _repeated_run(sents, i)
        if run:
            kept.extend(sents[i:i + run])
            dropped += run
            i += run * 2
            continue
        kept.append(sents[i])
        i += 1
    return "".join(kept), dropped


def _repeated_run(sents: list[str], start: int) -> int:
    """sents[start:] 开头是否立刻重复了某个句块，返回该块长度。"""
    limit = (len(sents) - start) // 2
    for size in range(limit, 0, -1):
        first = sents[start:start + size]
        if first == sents[start + size:start + size * 2] \
                and sum(len(s) for s in first) >= _MIN_DUP_SENT:
            return size
    return 0


def _footer_kind(line: str) -> str | None:
    """正文尾部侧栏行：程序行 / 关联法条行 / 纯装饰（返回 drop）。"""
    text = line.strip()
    if not text or all(ch in "#　 " for ch in text):
        return "drop"
    if _PROC_RE.match(text):
        return "proc"
    return "law" if _LAW_LINE_RE.match(text) else None


def _pull_footer(paras: list[str]) -> tuple[list[str], list[str], list[str]]:
    """把正文末尾的关联法条行与「一审/二审」行抽出来（人民法院案例库原文如此）。"""
    body = list(paras)
    laws: list[str] = []
    procs: list[str] = []
    # 关联索引之后常残留下一篇案例标题：仅当前一行确实是索引行时才丢弃
    trimmed = True
    while trimmed and len(body) >= 2:
        trimmed = (_TITLE_LINE.match(body[-1].strip()) is not None
                   and _footer_kind(_GAP.split(body[-2])[-1].strip()) is not None)
        if trimmed:
            body.pop()
    while body:
        chunks = [c.strip() for c in _GAP.split(body[-1]) if c.strip()]
        if not chunks:
            body.pop()
            continue
        taken: list[str] = []
        while chunks and _footer_kind(chunks[-1]):
            taken.insert(0, chunks.pop())
        if not taken:
            break
        for chunk in taken:
            if _footer_kind(chunk) == "law":
                laws.append(chunk)
            elif _footer_kind(chunk) == "proc":
                procs.append(chunk)
        if chunks:
            body[-1] = "".join(chunks)
            break
        body.pop()
    return body, laws[::-1], procs[::-1]


def _attach_footer(out: list[dict]) -> list[dict]:
    """无标题正文节 → 正文 + 相关法条 + 审理程序（后两者按序合并进同名小节）。"""
    if not out or out[-1]["label"] != "":
        return out
    body, laws, procs = _pull_footer(out[-1]["text"].splitlines())
    out = out[:-1] + ([{"label": "", "text": "\n".join(body)}] if body else [])
    for label, lines in (("相关法条", laws), ("审理程序", procs)):
        if not lines:
            continue
        existing = next((s for s in out if s["label"] == label), None)
        if existing:
            existing["text"] = existing["text"] + "\n" + "\n".join(lines)
        else:
            out.append({"label": label, "text": "\n".join(lines)})
    return out


def _reorder(sections: list[dict]) -> list[dict]:
    """关键词 / 要旨 / 相关法条 前置、审理程序置尾，其余保持原文顺序。"""
    head = [s for s in sections if s["label"] in _HEAD_LABELS]
    laws = [s for s in sections if s["label"] in _LAW_LABELS]
    tail = [s for s in sections if s["label"] in _TAIL_LABELS]
    middle = [s for s in sections
              if s["label"] not in _HEAD_LABELS + _LAW_LABELS + _TAIL_LABELS]
    return head + laws + middle + tail


def sections(text: str, title: str = "") -> tuple[list[dict], int]:
    """原文 → 文书小节；返回 (sections, 删除的重复段/句数)。

    传入 title 时，正文里重复出现的标题行会被去掉（最高法原文有该行）。
    """
    title_norm = re.sub(r"\s+", "", title or "")
    out = [{"label": label, "text": "\n".join(_merge_wrapped(lines)).strip()}
           for label, lines in _drop_leaked_tail(_split_groups(text))]
    out = _attach_footer(out)
    if out and out[0]["label"] == "":
        rest, summary = _lift_summary(out[0])
        if summary and rest["text"]:
            out = [summary, rest] + out[1:]
    out = _reorder(out)
    kept: list[dict] = []
    dropped = 0
    last_norm = ""
    for sec in out:
        paras: list[str] = []
        for para in sec["text"].splitlines():
            norm = re.sub(r"\s+", "", para)
            if norm and (norm == last_norm or (title_norm and norm == title_norm)):
                dropped += 1
                continue
            clean, dup = _dedupe_sentences(para)
            dropped += dup
            paras.append(clean)
            last_norm = norm
        if paras:
            kept.append({"label": sec["label"], "text": "\n".join(paras)})
    return kept, dropped


def _terms(q: str) -> list[str]:
    return [t for t in re.split(r"[\s、，,]+", (q or "").strip()) if t]


def _hits(row: dict, terms: list[str]) -> bool:
    return all(any(t in (row.get(f) or "") for f, _w in _FIELDS) for t in terms)


def _score(row: dict, terms: list[str]) -> int:
    score = sum(max((w for f, w in _FIELDS if t in (row.get(f) or "")), default=0)
                for t in terms)
    if all(t in row["title"] for t in terms):
        score += 4
    return score


def _snippet(row: dict, terms: list[str]) -> str:
    text = row.get("text") or ""
    idx = next((i for t in terms for i in [text.find(t)] if i >= 0), -1)
    if idx < 0:
        head = text[:_SNIPPET_PAD * 2]
        return head + ("…" if len(text) > len(head) else "")
    start = max(0, idx - _SNIPPET_PAD)
    end = min(len(text), idx + _SNIPPET_PAD)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def _sort_key(item: dict) -> tuple:
    return (-item["score"], not item["case_no"], _rev(item["date"]),
            item["source"], item["loc"])


def _rev(text: str) -> str:
    """日期降序：用码点取反的字符串参与升序排序，空值排最后。"""
    return "".join(chr(0x10FFFF - ord(c)) for c in text) if text else "\uffff"


def search(conn, q: str, source: str | None = None, limit: int = 30) -> list[dict]:
    """关键词模糊检索：多词 AND（全部命中），按字段权重排序，返回带片段的命中列表。"""
    terms = _terms(q)
    if not terms:
        return []
    sql = ("SELECT source, loc, title, category, case_no, keywords, date, url, text "
           "FROM cases")
    params: list[str] = []
    if source:
        sql += " WHERE source = ?"
        params.append(source)
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    items = []
    for row in rows:
        if not _hits(row, terms):
            continue
        item = {**row, "keywords": _keywords(row["keywords"])}
        item["score"] = _score(row, terms)
        item["snippet"] = _snippet(row, terms)
        item.pop("text")
        items.append(item)
    items.sort(key=_sort_key)
    return items[:limit]


def stats(conn) -> dict:
    """案例库总量与各来源条数。"""
    rows = conn.execute("SELECT source, COUNT(*) AS n FROM cases GROUP BY source")
    counts = {r["source"]: r["n"] for r in rows.fetchall()}
    return {"total": sum(counts.values()),
            "sources": [{"source": s, "n": counts.get(s, 0)} for s in CASE_SOURCES]}


def _keywords(raw) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []
