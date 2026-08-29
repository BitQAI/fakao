"""法条库（data/法条库/*.md）运行时解析：简称→文件、条号归一、条文正文查询。

只读数据源，不落库；解析结果内存缓存。兼容 `第X条　正文` 与 `**第X条**　正文`，
支持 `第二百八十七条之二` 子条。
"""
import re
from pathlib import Path

from app import config

# 法名简称 → 法条库文件名（无 .md；代码内维护，新增简称在此扩展）
STATUTE_ALIASES = {
    "刑法": "中华人民共和国刑法",
    "民法典": "中华人民共和国民法典",
    "民诉法": "中华人民共和国民事诉讼法",
    "民事诉讼法": "中华人民共和国民事诉讼法",
    "刑诉法": "中华人民共和国刑事诉讼法",
    "刑事诉讼法": "中华人民共和国刑事诉讼法",
    "宪法": "中华人民共和国宪法（2018年修正文本）",
    "公司法": "中华人民共和国公司法",
    "保险法": "中华人民共和国保险法",
    "证券法": "中华人民共和国证券法",
    "票据法": "中华人民共和国票据法",
    "企业破产法": "中华人民共和国企业破产法",
    "合伙企业法": "中华人民共和国合伙企业法",
    "监察法": "中华人民共和国监察法",
    "立法法": "中华人民共和国立法法",
    "行政处罚法": "中华人民共和国行政处罚法",
    "行政复议法": "中华人民共和国行政复议法",
    "行政强制法": "中华人民共和国行政强制法",
    "行政许可法": "中华人民共和国行政许可法",
    "行政诉讼法": "中华人民共和国行政诉讼法",
    "国家赔偿法": "中华人民共和国国家赔偿法",
    "仲裁法": "中华人民共和国仲裁法",
    "水污染防治法": "中华人民共和国水污染防治法",
    "环境保护法": "中华人民共和国环境保护法",
    "民营经济促进法": "民营经济促进法-全文",
    "刑事诉讼法解释": "最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释",
    "民事诉讼法解释": "最高人民法院关于适用《中华人民共和国民事诉讼法》的解释",
}

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ARTICLE_RE = re.compile(
    r"第?(?P<num>[0-9零一二三四五六七八九十百千]+)条"
    r"(?P<sub>之[零一二三四五六七八九十]+)?(?P<rest>.*)$"
)
_ARTICLE_LINE_RE = re.compile(
    r"^\**第(?P<num>[零一二三四五六七八九十百千]+)条"
    r"(?P<sub>之[零一二三四五六七八九十]+)?\**\s*[　 ]?(?P<body>.*)$"
)

_LAW_FILE_CACHE: dict[Path, dict[tuple[int, int], str]] = {}
_STATUTE_CACHE: dict[str, str | None] = {}


def _cn2int(s: str) -> int | None:
    """中文数字 → int（支持 零一二三四五六七八九十百千），阿拉伯数字原样返回。"""
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total, num = 0, 0
    for ch in s:
        if ch == "千":
            num = num or 1
            total += num * 1000
            num = 0
        elif ch == "百":
            num = num or 1
            total += num * 100
            num = 0
        elif ch == "十":
            total += (num or 1) * 10
            num = 0
        elif ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        else:
            return None
    return total + num


def parse_law_file(path: Path) -> dict[tuple[int, int], str]:
    """解析法条库 md：{(条号, 子条号): 条文正文}。"""
    if path in _LAW_FILE_CACHE:
        return _LAW_FILE_CACHE[path]
    articles: dict[tuple[int, int], str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = _ARTICLE_LINE_RE.match(line.strip())
        if not m:
            continue
        num = _cn2int(m.group("num"))
        sub = _cn2int(m.group("sub")[1:]) if m.group("sub") else 0
        if num is not None:
            articles[(num, sub)] = m.group("body").strip()
    _LAW_FILE_CACHE[path] = articles
    return articles


def resolve_law_file(law: str) -> Path | None:
    """法名简称 → 法条库文件路径；别名映射优先，其次尝试 中华人民共和国<法名>。"""
    name = STATUTE_ALIASES.get(law, law)
    for template in (name, f"中华人民共和国{law}"):
        p = config.STATUTE_DIR / f"{template}.md"
        if p.exists():
            return p
    return None


def resolve_statute(text: str) -> str | None:
    """"刑法269条"/"民法典第1165条"/"刑法287条之二"/"刑法第20条第3款" → 条文正文；
    条号后的款/项/目后缀忽略（返回整条正文）；解析不到返回 None。"""
    if text in _STATUTE_CACHE:
        return _STATUTE_CACHE[text]
    m = _ARTICLE_RE.search(text)
    if not m:
        _STATUTE_CACHE[text] = None
        return None
    law = text[: m.start()].strip()
    num = _cn2int(m.group("num"))
    sub = _cn2int(m.group("sub")[1:]) if m.group("sub") else 0
    body = None
    if law and num is not None:
        path = resolve_law_file(law)
        if path is not None:
            body = parse_law_file(path).get((num, sub))
    _STATUTE_CACHE[text] = body
    return body
