"""DeepSeek 客户端与全部规则兜底。

设计原则（spec 九）：LLM 故障时核心流程不中断，所有生成函数都有纯规则兜底。
"""
import json

from openai import AsyncOpenAI, OpenAI

from app import config

SYSTEM_COACH = (
    "你是法考客观题冲刺教练。回答简洁、口语化、面向手机阅读，"
    "引用法条时给出条文号。用户时间极紧，不要长篇大论。"
)


def get_client() -> OpenAI | None:
    if not config.DEEPSEEK_API_KEY:
        return None
    return OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)


def get_async_client() -> AsyncOpenAI | None:
    if not config.DEEPSEEK_API_KEY:
        return None
    return AsyncOpenAI(api_key=config.DEEPSEEK_API_KEY,
                       base_url=config.DEEPSEEK_BASE_URL)


def call_llm(system: str, user: str, temperature: float = 0.3,
             max_tokens: int = 1200) -> str | None:
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception:  # noqa: BLE001 - 网络/限流一律兜底
        return None


def adjust_plan_ratio(stats: dict) -> float:
    """今日队列中新学条目占比：剩余天数越少越高，夹在 [0.1, 0.6]。"""
    text = call_llm(
        "你是法考备考规划师。根据统计 JSON 返回一个 0~1 之间的数字："
        "今天队列中「新学条目」应占的比例。剩余天数越少，新学占比越高以保证覆盖，"
        "但不超过 0.6。只输出数字，不要任何其他文字。",
        json.dumps(stats, ensure_ascii=False),
        temperature=0.2,
        max_tokens=50,
    )
    try:
        value = float(text.strip())
    except Exception:  # noqa: BLE001
        return 0.35
    return max(0.1, min(0.6, value))


def generate_daily_rationale(stats: dict) -> str:
    template = (
        f"距考试 {stats.get('days_left', '?')} 天：今日计划 {stats.get('quota', 0)} 条"
        f"（新学 {stats.get('new_n', 0)} / 复习 {stats.get('review_n', 0)}"
        f" / 错题 {stats.get('retry_n', 0)}），"
        f"按「剩余天数 × 容量 × 总量」动态配比。"
    )
    text = call_llm(
        SYSTEM_COACH,
        "用一句话解释今天的学习安排（给出配比理由），数据："
        + json.dumps(stats, ensure_ascii=False),
        max_tokens=120,
    )
    return (text or "").strip() or template


def generate_evening_report(stats: dict) -> str:
    template = (
        f"## 今日复盘（{stats.get('date', '')}）\n\n"
        f"- 完成度：{stats.get('done', 0)}/{stats.get('quota', 0)}"
        f"（{stats.get('percent', 0)}%）\n"
        f"- 自测：{stats.get('quiz_correct', 0)}/{stats.get('quiz_total', 0)} 对\n"
        f"- 听学：约 {stats.get('listen_min', 0)} 分钟\n"
        f"- 薄弱：{stats.get('weak', '暂无')}\n"
        f"- 明日建议：优先复习错题 {stats.get('wrong', 0)} 条，"
        f"距考试 {stats.get('days_left', '?')} 天。\n"
    )
    text = call_llm(
        SYSTEM_COACH,
        "根据以下今日学习统计生成晚报（Markdown，5 行以内，含完成度、薄弱点、明日建议）："
        + json.dumps(stats, ensure_ascii=False),
        max_tokens=600,
    )
    return (text or "").strip() or template


def generate_morning_report(plan: dict, stats: dict) -> str:
    template = (
        f"早上好。距考试 {stats.get('days_left', '?')} 天。"
        f"今日 {plan.get('quota', 0)} 条：新学 {plan.get('new_n', 0)}、"
        f"复习 {plan.get('review_n', 0)}、错题 {plan.get('retry_n', 0)}。"
        f"先复习错题，再推进新内容。"
    )
    text = call_llm(
        SYSTEM_COACH,
        "生成早报（3 行以内，含今日计划、重点提醒）："
        + json.dumps({"plan": plan, "stats": stats}, ensure_ascii=False),
        max_tokens=400,
    )
    return (text or "").strip() or template


def generate_quiz(entry: dict) -> dict | None:
    text = call_llm(
        SYSTEM_COACH,
        "根据该条目出一道法考客观题（题干用场景，正确项来自结论句，"
        "干扰项来自易混淆情形）。约 1/3 出多选题（答案 2~3 个字母），其余单选。"
        "必须附带 30~60 字解析。只输出 JSON："
        '{"qtype": "choice"|"multi", "stem": "...", '
        '"options": ["A. ...", "B. ...", "C. ...", "D. ..."], '
        '"answer": "A"|"AB", "analysis": "..."}',
        temperature=0.5,
        max_tokens=400,
    )
    if not text:
        return None
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(cleaned)
        if not (data.get("stem") and len(data.get("options", [])) >= 2 and data.get("answer")):
            return None
        answer = data["answer"].strip().upper()
        letters = sorted(set(answer))
        if not all(0 <= ord(ch) - 65 < len(data["options"]) for ch in letters):
            return None
        # 题库统一存 choice：前端按答案长度区分单选/多选，LLM 的 multi 归一化，
        # 避免违反 quizzes.qtype CHECK('choice','cloze')。
        data["qtype"] = "choice"
        data["answer"] = "".join(letters)
        data["analysis"] = (data.get("analysis") or "").strip() \
            or f"正确答案：{''.join(letters)}。"
        return data
    except Exception:  # noqa: BLE001
        return None


def generate_quiz_analysis(quiz: dict) -> str | None:
    """为存量旧题补生成解析；失败返回 None（调用方给兜底文案）。"""
    text = call_llm(
        SYSTEM_COACH,
        "为这道法考题目写 30~60 字解析（说明正确项为何对、易错项为何错），只输出 JSON："
        '{"analysis": "..."}\n题目：'
        + json.dumps({k: quiz.get(k) for k in ("stem", "options", "answer")},
                     ensure_ascii=False),
        temperature=0.3,
        max_tokens=200,
    )
    if not text:
        return None
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(cleaned)
        return (data.get("analysis") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def cloze_quiz(entry: dict) -> dict:
    conclusion = entry["conclusion"]
    tail_len = 6 if len(conclusion) > 8 else 0
    stem = f"{entry['anchor']}。请补全结论：{conclusion[:-tail_len]}____"
    return {"qtype": "cloze", "stem": stem, "options": [],
            "answer": conclusion, "analysis": conclusion}


def generate_talk(subject: str, entries: list[dict]) -> str | None:
    brief = "；".join(
        f"{e['point']}：{e['conclusion']}" for e in entries[:40]
    )
    text = call_llm(
        SYSTEM_COACH,
        f"把下列{subject}条目串成 3~5 分钟的口播讲稿（像播客，先总述再逐条，"
        "口语化、带停顿提示）：\n" + brief,
        temperature=0.7,
        max_tokens=1600,
    )
    return text


async def stream_answer(question: str, context_text: str):
    client = get_async_client()
    if client is None:
        yield "AI 助手未配置（缺少 DeepSeek key），请到「我的」页配置后重试。"
        return
    try:
        stream = await client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_COACH
                 + " 只能基于提供的资料回答，不确定就明说；引用条目时标注其 ID。"},
                {"role": "user", "content": f"参考资料：\n{context_text}\n\n问题：{question}"},
            ],
            stream=True,
            temperature=0.3,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception:  # noqa: BLE001
        yield "\n\n（AI 服务暂时不可用，请稍后重试；今日队列与复盘不受影响。）"
