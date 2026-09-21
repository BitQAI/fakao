"""主观题生成脚本的共享工具：JSON 抽取、采分点清洗、材料清洗、写库。

三个生成脚本（案例分析 / 论述题 / 综合大案例）共用这里的校验与落库，
避免三份重复实现。业务差异只体现在「允许的维度」「是否必须写法条」两个参数上。
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ai, statutes  # noqa: E402

#: 材料标签：材料一 / 材料二 / 材料三
_LABELS = ("材料一", "材料二", "材料三", "材料四", "材料五")


def extract_json(text: str) -> dict | None:
    """从 LLM 输出里抠出 JSON（容忍 ``` 围栏与前后废话）。"""
    if not text:
        return None
    body = re.sub(r"```(?:json)?", "", text).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return None


def llm_json(system: str, user: str, temperature: float = 0.4,
             max_tokens: int = 1400) -> dict | None:
    """调 LLM 并抽 JSON。

    主观题的输出较长（长案情 + 十几个采分点），默认额度容易把 JSON 截断成
    不可解析；解析失败时用更大额度重试一次，仍失败才放弃。
    """
    data = extract_json(ai.call_llm(system, user, temperature=temperature,
                                    max_tokens=max_tokens))
    if data is not None:
        return data
    return extract_json(ai.call_llm(system, user, temperature=temperature,
                                    max_tokens=max_tokens + 1600))


def llm_json_checked(system: str, user: str, check, attempts: int = 3,
                     temperature: float = 0.4,
                     max_tokens: int = 1400) -> tuple[dict | None, list[str]]:
    """生成 → 校验 → 把校验问题回喂给模型重试。

    长输出（综合大案例）常出现「字数超标 / 点数超标 / 忘了写法条」，
    单纯丢弃太浪费；把问题列回去让它自己改，成功率明显更高。
    返回 (通过校验的题目, 问题列表)。
    """
    prompt = user
    problems: list[str] = []
    for i in range(attempts):
        data = llm_json(system, prompt, temperature=temperature,
                        max_tokens=max_tokens + i * 800)
        if data is None:
            problems = ["输出不是合法 JSON（可能被截断）"]
        else:
            fixed, problems = check(data)
            if fixed is not None:
                return fixed, []
        prompt = user + (
            f"\n\n【上一次输出不合格，请修正后重新输出完整 JSON，"
            f"本次是第 {i + 2} 次尝试】\n"
            + "\n".join(f"- {p}" for p in problems[:6]))
    return None, problems


def clean_points(points: list, kinds: tuple[str, ...],
                 must_cite: tuple[str, ...] = ("依据",), relax: bool = False,
                 qno_max: int | None = None) -> tuple[list[dict], list[str]]:
    """校验并清洗采分点，返回 (采分点, 问题列表)。

    - kinds：该题型允许的维度（案例分析 6 维 / 论述题 5 维）；
    - must_cite：必须写出可解析法条的维度（论述题传空元组：法治思想无条文骨架）；
    - relax：允许法条暂不可解析（法条库补全前用），该点标记 verified=False；
    - qno_max：传入小问数时，采分点必须带 1..qno_max 的 qno（综合大案例按小问分组）。
    """
    problems: list[str] = []
    clean: list[dict] = []
    for i, p in enumerate(points or [], 1):
        if not isinstance(p, dict) or not str(p.get("text") or "").strip():
            problems.append(f"第 {i} 个采分点缺少 text")
            continue
        kind = str(p.get("kind") or "").strip()
        if kind not in kinds:
            problems.append(f"第 {i} 个采分点 kind 非法：{kind or '空'}")
            continue
        refs = [str(s).strip() for s in (p.get("statutes") or []) if str(s).strip()]
        ok = [s for s in refs if statutes.resolve_statute(s)]
        if kind in must_cite and not refs:
            problems.append(f"第 {i} 个采分点没写法条依据")
        elif kind in must_cite and not ok and not relax:
            problems.append(f"第 {i} 个采分点法条均不可解析：{refs}")
        item = {"no": i, "kind": kind, "text": str(p["text"]).strip(),
                "statutes": refs, "verified": bool(ok)}
        if qno_max is not None:
            qno = p.get("qno")
            if not isinstance(qno, int) or not 1 <= qno <= qno_max:
                problems.append(f"第 {i} 个采分点 qno 非法：{qno!r}")
                continue
            item["qno"] = qno
        clean.append(item)
    return clean, problems


def clean_materials(materials: list, min_len: int,
                    max_len: int) -> tuple[list[dict], list[str]]:
    """材料 → [{"label": "材料一", "text": …}]；标签按顺序给，不采信 LLM 起的名字。"""
    problems: list[str] = []
    clean: list[dict] = []
    for i, m in enumerate(materials or []):
        text = str(m.get("text") if isinstance(m, dict) else m or "").strip()
        if not min_len <= len(text) <= max_len:
            problems.append(f"第 {i + 1} 段材料长度 {len(text)} 不在 {min_len}-{max_len}")
            continue
        clean.append({"label": _LABELS[i] if i < len(_LABELS) else f"材料{i + 1}",
                      "text": text})
    return clean, problems


def missing_kinds(points: list[dict], required: tuple[str, ...]) -> list[str]:
    """检查采分点是否覆盖指定维度（如论述题必须有 总论点/材料结合/实践措施）。"""
    have = {p["kind"] for p in points}
    return [k for k in required if k not in have]


def save_question(conn, *, case_source: str, case_loc: str, subject: str, qtype: str,
                  stem: str, questions: list, points: list, reference: str,
                  materials: list | None = None) -> int:
    """落库为 draft（发布需人工抽检后调用 publish）。返回新题 id，重复则 0。"""
    cur = conn.execute(
        "INSERT OR IGNORE INTO case_questions (case_source, case_loc, subject, qtype,"
        " stem, questions, points, materials, reference, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,'draft',?)",
        (case_source, case_loc, subject, qtype, stem,
         json.dumps(questions, ensure_ascii=False),
         json.dumps(points, ensure_ascii=False),
         json.dumps(materials or [], ensure_ascii=False),
         reference, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    # INSERT OR IGNORE 被忽略时 changes=0，此时 lastrowid 仍会指向旧行，必须靠 rowcount 区分
    return (cur.lastrowid or 0) if cur.rowcount else 0


def publish(conn, qtype: str | None = None) -> int:
    """把 draft 置为 published；给 qtype 时只发布该题型。"""
    if qtype:
        cur = conn.execute("UPDATE case_questions SET status='published'"
                           " WHERE status='draft' AND qtype=?", (qtype,))
    else:
        cur = conn.execute("UPDATE case_questions SET status='published'"
                           " WHERE status='draft'")
    conn.commit()
    return cur.rowcount
