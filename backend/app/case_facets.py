"""案例库分面聚合（只读）：部门法 / 罪名 / 年份 / 来源库。

口径见 docs/superpowers/specs/2026-09-22-案例库分面筛选与浏览-design.md ：
主部门法固定取 keywords[0]（format_cases 生成时把标签放在首位），
罪名取 keywords 中以「罪」结尾的词，年份取 date 前 4 位。
"""
from __future__ import annotations

import json

from app.cases import CASE_SOURCES

# 部门法标签（与 format_cases._derive_keywords 的 tag 取值一致）
FIELD_TAGS = ("刑事", "民事", "行政", "执行", "国家赔偿")
# 未打上部门法标签的兜底桶
UNLABELED = "未标注"
# 以「罪」结尾但不是罪名的词，不进罪名维度
EXCLUDED_CRIMES = {"无罪", "有罪", "犯罪"}


def case_year(date: str) -> str:
    """案例日期 → 4 位年份；非法或缺失返回空串。"""
    text = (date or "").strip()
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""


def crimes_of(keywords: list[str]) -> list[str]:
    """关键词里的罪名（以「罪」结尾，剔除无罪/有罪/犯罪）。"""
    return [k for k in keywords
            if isinstance(k, str) and k.endswith("罪") and k not in EXCLUDED_CRIMES]


def field_of(keywords: list[str]) -> str:
    """主部门法：keywords[0] 命中标签时取该标签，否则算未标注。"""
    return keywords[0] if keywords and keywords[0] in FIELD_TAGS else UNLABELED


def _keywords(raw) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def facets(conn) -> dict:
    """单趟扫描聚合四类分面；字段/罪名按频次降序，年份按年份倒序。"""
    fields: dict[str, int] = {}
    crimes: dict[str, int] = {}
    years: dict[str, int] = {}
    sources: dict[str, int] = {}
    total = 0
    for row in conn.execute("SELECT source, keywords, date FROM cases"):
        total += 1
        sources[row["source"]] = sources.get(row["source"], 0) + 1
        keywords = _keywords(row["keywords"])
        field_key = field_of(keywords)
        fields[field_key] = fields.get(field_key, 0) + 1
        for crime in crimes_of(keywords):
            crimes[crime] = crimes.get(crime, 0) + 1
        year = case_year(row["date"])
        if year:
            years[year] = years.get(year, 0) + 1
    return {
        "total": total,
        "scanned": total,
        "fields": _by_order(fields, FIELD_TAGS + (UNLABELED,)),
        "crimes": _by_count(crimes),
        "years": _by_year(years),
        "sources": [{"value": s, "n": sources.get(s, 0)} for s in CASE_SOURCES],
    }


def _by_order(counts: dict[str, int], order: tuple[str, ...]) -> list[dict]:
    """按固定顺序输出（缺失补 0），保证前端 chips 顺序稳定。"""
    return [{"value": key, "n": counts.get(key, 0)} for key in order]


def _by_count(counts: dict[str, int]) -> list[dict]:
    """频次降序，同频按字典序。"""
    keys = sorted(counts, key=lambda k: (-counts[k], k))
    return [{"value": key, "n": counts[key]} for key in keys]


def _by_year(counts: dict[str, int]) -> list[dict]:
    """年份倒序（新的在前），只含能解析出年份的案例。"""
    keys = sorted(counts, reverse=True)
    return [{"value": key, "n": counts[key]} for key in keys]
