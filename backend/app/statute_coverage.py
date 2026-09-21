"""法条覆盖率度量：每部法「条文总数 / 被条目引用 / 被题目覆盖」。

用途：检验「法条补全」是否真的变成了题库资产——法条库补全后，若某部法的条文
既没被条目引用、也没被任何题目覆盖，就说明这部法还没进入训练闭环。

口径：
- 条文总数：`app/statute_index` 解析出的条文数（含子条）；
- 被条目引用：条目 `statutes` 字段能解析到该法该条的条数；
- 被题目覆盖：**已发布**题库题（`quizzes.basis`，status='published'）能解析到该法该条的条数
  （客观题与判断题都算）；draft 是生成中间态、archived 是下架题，用户练不到，不计入；
- 覆盖率 = 被题目覆盖条文数 / 条文总数。
"""
import json

from app import config, statute_index, statutes


def category(law_key: str) -> str:
    """按法名归类，便于报告里分块看覆盖率。"""
    key = law_key or ""
    if any(word in key for word in ("公约", "协定", "议定书", "宪章", "规约", "条约",
                                    "通则", "惯例", "谅解", "GATT", "UCP")):
        return "国际条约"
    if key.startswith("最高人民法院") or key.startswith("最高人民检察院") or \
            any(word in key for word in ("解释", "规定的", "意见", "纪要", "规则")):
        return "司法解释与配套"
    if key.endswith("条例"):
        return "行政法规"
    return "法律"


def _refs(rows, field: str) -> dict[str, set[tuple[int, int]]]:
    """把条目 statutes / 题目 basis 解析成 {法条库主名: {(条号, 子条号)}}。"""
    out: dict[str, set[tuple[int, int]]] = {}
    for value in rows:
        items = json.loads(value) if value and value.startswith("[") else [value]
        for text in items:
            if not text:
                continue
            located = statutes.resolve_law_article(str(text))
            if located is None:
                continue
            key, no, sub = located
            out.setdefault(key, set()).add((no, sub))
    return out


def coverage(conn, directory=None) -> list[dict]:
    """返回每部法的覆盖率统计（按覆盖率升序，缺口大的在前）。"""
    library = statute_index.load_library(directory or config.STATUTE_DIR)
    cited = _refs((r["statutes"] for r in conn.execute(
        "SELECT statutes FROM v_entries WHERE status='final'")), "statutes")
    covered = _refs((r["basis"] for r in conn.execute(
        "SELECT basis FROM quizzes WHERE basis != '' AND status='published'")),
        "basis")
    out = []
    for key, law in library.items():
        valid = {(a.no, a.sub) for a in law.articles}
        cited_set = cited.get(key, set()) & valid
        covered_set = covered.get(key, set()) & valid
        total = len(valid)
        out.append({
            "key": key,
            "name": law.name,
            "category": category(key),
            "articles": total,
            "cited": len(cited_set),
            "covered": len(covered_set),
            "cited_and_covered": len(cited_set & covered_set),
            "coverage": round(len(covered_set) / total, 4) if total else 0.0,
        })
    return sorted(out, key=lambda r: (r["coverage"], -r["articles"]))


def summary(rows: list[dict]) -> dict:
    """总量与分类汇总。"""
    by_category: dict[str, dict] = {}
    for row in rows:
        bucket = by_category.setdefault(row["category"], {
            "laws": 0, "articles": 0, "covered": 0, "laws_with_question": 0})
        bucket["laws"] += 1
        bucket["articles"] += row["articles"]
        bucket["covered"] += row["covered"]
        if row["covered"]:
            bucket["laws_with_question"] += 1
    total = {
        "laws": len(rows),
        "articles": sum(r["articles"] for r in rows),
        "covered": sum(r["covered"] for r in rows),
        "cited": sum(r["cited"] for r in rows),
        "laws_with_question": sum(1 for r in rows if r["covered"]),
    }
    total["coverage"] = (round(total["covered"] / total["articles"], 4)
                         if total["articles"] else 0.0)
    return {"total": total, "by_category": by_category}


def uncovered_articles(law_key: str, covered: set[tuple[int, int]],
                       directory=None) -> list:
    """某部法里尚未被任何题覆盖的条文（供补题脚本挑候选）。"""
    library = statute_index.load_library(directory or config.STATUTE_DIR)
    law = library.get(law_key)
    if law is None:
        return []
    return [a for a in law.articles if (a.no, a.sub) not in covered]
