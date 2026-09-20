"""法条库全量索引：目录树、条文检索、条目反向索引。

与 app/statutes.py 分工：statutes.py 负责「简称 → 文件 → 单条正文」的按需解析；
本模块负责全量索引与检索，两者共用数字转换与条号正则，不重复实现。
只读数据源，解析结果内存缓存。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app import config, statutes

#: 编 / 章 / 节 三级标题
_LEVEL_RES = (
    (1, re.compile(r"^第([零一二三四五六七八九十百千]+)编[　\s]*(.*)$")),
    (2, re.compile(r"^第([零一二三四五六七八九十百千]+)章[　\s]*(.*)$")),
    (3, re.compile(r"^第([零一二三四五六七八九十百千]+)节[　\s]*(.*)$")),
)
#: 「一、管辖」式标题（民诉解释等），限长且不带句号，避免误吃条文正文
_NUMBERED_RE = re.compile(r"^([一二三四五六七八九十]{1,3})、[　\s]*(.{1,20})$")
_TOC_RE = re.compile(r"^目[　\s]*录$")
_CN_DIGITS = "零一二三四五六七八九十"

_CACHE: dict[str, "Law"] | None = None
_LIB_DIR: Path | None = None


@dataclass(frozen=True)
class Article:
    """一条法条。sub 为子条号（如「第287条之二」的 sub=2）。"""

    no: int
    sub: int
    text: str
    chapter: tuple[str, ...]

    @property
    def label(self) -> str:
        base = f"第{int2cn(self.no)}条"
        return f"{base}之{_CN_DIGITS[self.sub]}" if self.sub else base


@dataclass(frozen=True)
class Law:
    key: str          # 文件主名，稳定标识（与 STATUTE_ALIASES 的取值一致）
    name: str         # 展示名（取自文件首个一级标题）
    path: Path
    meta: dict[str, str]
    articles: tuple[Article, ...]

    def article(self, no: int, sub: int = 0) -> Article | None:
        for a in self.articles:
            if a.no == no and a.sub == sub:
                return a
        return None


def int2cn(n: int) -> str:
    """整数 → 中文条号写法（10 → 十，287 → 二百八十七）。"""
    if n <= 0:
        return str(n)
    units = ["", "十", "百", "千"]
    parts: list[str] = []
    digits = [int(d) for d in str(n)]
    size = len(digits)
    for i, d in enumerate(digits):
        pos = size - i - 1
        if d == 0:
            if parts and not parts[-1].endswith("零") and any(x != 0 for x in digits[i:]):
                parts.append("零")
            continue
        if pos == 1 and d == 1 and not parts:
            parts.append("十")
        else:
            parts.append(_CN_DIGITS[d] + units[pos])
    return "".join(parts) or "零"


def _split_meta(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in re.split(r"\s{2,}", line.lstrip("-").strip()):
        if "：" in chunk:
            k, _, v = chunk.partition("：")
            out[k.strip()] = v.strip()
    return out


def _heading(line: str) -> tuple[int, str] | None:
    for level, rx in _LEVEL_RES:
        m = rx.match(line)
        if m:
            return level, line
    if line.endswith("。"):
        return None
    m = _NUMBERED_RE.match(line)
    if m:
        return 2, line
    return None


def parse_law(path: Path) -> Law:
    """解析单个法条库文件：跳过目录段，按标题层级归属条文，收全多段正文。"""
    name = path.stem
    meta: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    articles: list[Article] = []
    buf: list[str] = []
    key: tuple[int, int] | None = None
    head = True

    def flush() -> None:
        nonlocal buf, key
        if key is not None:
            text = "\n".join(buf).strip()
            if text:
                articles.append(Article(key[0], key[1], text,
                                        tuple(t for _, t in stack)))
        buf, key = [], None

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        if head and line.startswith("- "):
            meta.update(_split_meta(line))
            continue
        if head and line.startswith("# "):
            name = line[2:].strip()
            continue
        if _TOC_RE.match(line):
            continue
        hd = _heading(line)
        if hd is not None:
            level, text = hd
            head = False
            flush()
            stack[:] = [(lv, t) for lv, t in stack if lv < level]
            stack.append((level, text))
            continue
        m = statutes._ARTICLE_LINE_RE.match(line)
        if m:
            num = statutes._cn2int(m.group("num"))
            if num is not None:
                flush()
                head = False
                sub = statutes._cn2int(m.group("sub")[1:]) if m.group("sub") else 0
                key = (num, sub or 0)
                body = m.group("body").strip()
                buf = [body] if body else []
                continue
        if key is not None:
            buf.append(line)
    flush()
    return Law(key=path.stem, name=name, path=path, meta=meta,
               articles=tuple(articles))


def load_library(directory: Path | None = None) -> dict[str, Law]:
    """加载全部法条库（按文件主名索引），结果内存缓存。"""
    global _CACHE, _LIB_DIR
    directory = directory or config.STATUTE_DIR
    if _CACHE is not None and _LIB_DIR == directory:
        return _CACHE
    laws: dict[str, Law] = {}
    if directory.exists():
        for path in sorted(directory.glob("*.md")):
            if path.name.startswith("_"):
                continue
            laws[path.stem] = parse_law(path)
    _CACHE, _LIB_DIR = laws, directory
    return laws


def clear_cache() -> None:
    """清空缓存（测试或数据变更后调用）。"""
    global _CACHE, _LIB_DIR
    _CACHE, _LIB_DIR = None, None
    statutes._LAW_FILE_CACHE.clear()
    statutes._STATUTE_CACHE.clear()


def list_laws(directory: Path | None = None) -> list[dict]:
    """法名清单：key / 展示名 / 条数 / 元信息。"""
    return [{
        "key": law.key, "name": law.name,
        "articles": len(law.articles), "meta": law.meta,
    } for law in load_library(directory).values()]


def law_payload(key: str, offset: int = 0, limit: int = 200,
                directory: Path | None = None) -> dict | None:
    """单部法律的目录 + 条文分页。key 支持文件主名，也支持条目里用的简称。"""
    library = load_library(directory)
    law = library.get(key)
    if law is None:
        path = statutes.resolve_law_file(key)
        law = library.get(path.stem) if path is not None else None
    if law is None:
        return None
    items = [{
        "no": a.no, "sub": a.sub, "label": a.label,
        "text": a.text, "chapter": list(a.chapter),
    } for a in law.articles[offset:offset + limit]]
    chapters: list[str] = []
    for a in law.articles:
        for c in a.chapter:
            if c not in chapters:
                chapters.append(c)
    return {"key": law.key, "name": law.name, "meta": law.meta,
            "total": len(law.articles), "offset": offset,
            "chapters": chapters, "items": items}


def search(q: str, limit: int = 30, context: int = 24,
           directory: Path | None = None) -> list[dict]:
    """条文全文检索，返回命中片段（居中截取）。"""
    q = (q or "").strip()
    if not q:
        return []
    out: list[dict] = []
    for law in load_library(directory).values():
        for a in law.articles:
            idx = a.text.find(q)
            if idx < 0:
                continue
            start = max(0, idx - context)
            end = min(len(a.text), idx + len(q) + context)
            snippet = ("…" if start else "") + a.text[start:end] + (
                "…" if end < len(a.text) else "")
            out.append({"law": law.key, "law_name": law.name, "no": a.no,
                        "sub": a.sub, "label": a.label, "snippet": snippet,
                        "chapter": list(a.chapter)})
            if len(out) >= limit:
                return out
    return out


def short_names(law_key: str) -> list[str]:
    """条目的 statutes 字段里可能使用的法名写法（长名优先，避免误匹配）。"""
    names = {law_key, law_key.replace("中华人民共和国", "")}
    for alias, target in statutes.STATUTE_ALIASES.items():
        if target == law_key:
            names.add(alias)
    return sorted((n for n in names if n), key=len, reverse=True)


def entries_for(conn, law_key: str, no: int) -> list[dict]:
    """反向索引：引用了「法名 + 该条」的 final 条目。"""
    clauses: list[str] = []
    params: list = []
    for n in short_names(law_key):
        clauses.append("statutes LIKE ?")
        params.append(f"%{n}第{no}条%")
        clauses.append("statutes LIKE ?")
        params.append(f"%{n}{no}条%")
    if not clauses:
        return []
    rows = conn.execute(
        "SELECT id, subject, submodule, point, priority FROM entries "
        f"WHERE status='final' AND ({' OR '.join(clauses)}) "
        "ORDER BY subject, id", params).fetchall()
    return [{"id": r["id"], "subject": r["subject"],
             "submodule": r["submodule"], "point": r["point"],
             "priority": r["priority"]} for r in rows]
