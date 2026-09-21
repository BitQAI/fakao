"""数字表达抽取与比对：判「数相关」判断题的质量闸门。

用法：判断题生成后，必须满足
- answer=对：题干里的数字表达全部能在依据原文（法条/结论）中找到
- answer=错：题干里有且仅有少量数字表达不在原文中（即被改写的那处）
不满足即丢弃，避免 LLM 编造数字。

口径说明：
- 忽略条目号（「第91条」）与年份（≥1900 的「年」），它们不是考点数字；
- 阿拉伯数字与中文数字统一折算成整数后比较（「三十日」==「30日」）。
"""
import re

NUM = r"(?:\d+(?:\.\d+)?|[〇零一二三四五六七八九十百千万两]+)"
UNIT = (r"(?:个工作日|工作日|个月|周岁|小时|分钟|平方米|万元|亿元|"
        r"日|天|月|年|元|人|户|份|倍|次|岁|米|克|吨|件|项|种|名|部|张|股|座|%|％)")
BOUND = r"(?:以上|以下|以内|之外)?"
_TERM_RE = re.compile(rf"(?P<num>{NUM})\s*(?P<unit>{UNIT})(?P<bound>{BOUND})")
_PERCENT_RE = re.compile(rf"百分之(?P<num>{NUM})\s*(?P<bound>{BOUND})")
_FRACTION_RE = re.compile(rf"(?P<den>{NUM})分之(?P<num>{NUM})")
_ARTICLE_NO_RE = re.compile(r"第[〇零一二三四五六七八九十百千万0-9]+条")

_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def chinese_to_int(text: str) -> int | None:
    """中文数字转整数（支持「三十」「一百二十」「三千五百」「十万」等）。"""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    number = 0
    for ch in text:
        if ch in _DIGITS:
            number = _DIGITS[ch]
        elif ch in _UNITS:
            unit = _UNITS[ch]
            if unit == 10000:
                multiplier = section + number
                section = (multiplier or 1) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        else:
            return None
    return total + section + number


def extract(text: str) -> set[tuple[float, str, str]]:
    """抽取 (数值, 单位, 边界词) 三元组；忽略条目号与年份。"""
    if not text:
        return set()
    cleaned = _ARTICLE_NO_RE.sub("", text)
    out: set[tuple[float, str, str]] = set()
    for m in _PERCENT_RE.finditer(cleaned):
        value = chinese_to_int(m.group("num"))
        if value is not None:
            out.add((float(value), "%", m.group("bound") or ""))
    # 「百分之X」已按百分比计，避免被分数正则重复计为 X/100
    rest = _PERCENT_RE.sub("", cleaned)
    for m in _FRACTION_RE.finditer(rest):
        den, num = chinese_to_int(m.group("den")), chinese_to_int(m.group("num"))
        if den and num is not None:
            out.add((round(num / den, 4), "比例", ""))
    for m in _TERM_RE.finditer(cleaned):
        value = chinese_to_int(m.group("num"))
        if value is None:
            continue
        unit = "%" if m.group("unit") == "％" else m.group("unit")
        if unit == "年" and value >= 1900:      # 法条公布/修正年份不是考点
            continue
        # 「三日以内」与「三日内」等价，统一成无边界词，避免误判为改写
        bound = m.group("bound") or ""
        out.add((float(value), unit, "" if bound == "以内" else bound))
    return out


def fabricated(stem: str, reference: str) -> set[tuple[float, str, str]]:
    """题干里出现、但依据原文中没有的数字表达（被改写的部分）。"""
    return extract(stem) - extract(reference)


def is_grounded(stem: str, reference: str, answer: str,
                max_fabricated: int = 1) -> tuple[bool, str]:
    """校验判断题的数字是否与依据原文一致。

    - 「对」题：不允许出现原文没有的数字（max_fabricated 忽略字段仅在「错」题生效）
    - 「错」题：至少 1 处、至多 max_fabricated 处数字与原文不符
    """
    stem_nums = extract(stem)
    if not stem_nums:
        return False, "题干无数字表达"
    extra = fabricated(stem, reference)
    if answer == "对":
        if extra:
            return False, f"「对」题含原文外的数字 {sorted(extra)}"
        return True, ""
    if not extra:
        return False, "「错」题未改写任何数字"
    if len(extra) > max_fabricated:
        return False, f"「错」题改写了 {len(extra)} 处数字（上限 {max_fabricated}）"
    return True, ""
