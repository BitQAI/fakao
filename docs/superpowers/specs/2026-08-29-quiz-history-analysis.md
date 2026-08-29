# Spec：自测解析必达 + 做题历史（含当时选项）

- 日期：2026-08-29
- 状态：待评审
- 涉及模块：backend（service / routers/quizzes）、frontend（QuizView / types.ts / globals.css）、tests

## 1. 问题背景

1. **自测解析不保证**：新代码已让当日题目带解析（LLM 生成 + 兜底），但兜底文案单薄（仅"正确答案：X。"），且存量 `quizzes` 表历史行大多 `analysis=''`；一旦 LLM 失败或历史题被复用，解析可能缺失或信息量不足。用户要求**自测必须有解析**。
2. **无做题历史**：`quiz_answers` 表实际已保存每次答题（用户选项字母、对错、时间），但没有任何页面能看到；用户要求**能看到自己做过的题目，包括当时的选项**。

## 2. 方案概要

### 2.1 解析必达

- `service.ensure_quiz_analysis(conn, quiz)` 统一保证：`analysis` 非空直接返回；为空先 LLM 懒生成；失败用兜底——
  - 选择题：`正确答案：X。考点结论：<entry.conclusion>`
  - 填空题：结论全文
  - 生成后回写 `quizzes.analysis`。
- `build_daily_quiz`、`POST /api/quiz/answer`、`GET /api/quiz/history` 三处统一接入，输出恒有解析。
- 前端答题结果区做防御性兜底：`analysis` 缺失时展示 `正确答案：X`。

### 2.2 做题历史

- 数据复用 `quiz_answers JOIN quizzes`，无表结构变更。
- 新接口 `GET /api/quiz/history?limit=50`：返回最近 N 条记录，含时间、题型、题干、选项、正确答案、用户所选字母与对应选项文本、对错、解析。
- 前端自测页顶部增加「今日 / 历史」切换；历史列表逐条卡片：时间、题干、选项（正确项绿框 + ✓，误选项红框 + ✗）、正确答案、解析。

## 3. 数据模型

无变更（`quiz_answers` 已有 `user_answer`/`correct`/`ts`）。

## 4. API

### `GET /api/quiz/history?limit=50`

响应：
```json
{"items": [{
  "answer_id": 7, "quiz_id": 17, "ts": "2026-08-29T19:16:35",
  "user_answer": "AB", "picked_texts": ["A. ...", "B. ..."],
  "correct": true, "qtype": "choice", "stem": "...",
  "options": ["A. ...", "..."], "answer": "AB", "analysis": "..."
}]}
```

## 5. 验证标准

1. 任意题目（含存量 `analysis=''` 的题）在答题、今日题、历史三处输出均非空解析。
2. 历史接口返回用户当时的选项文本与对错。
3. `pytest` 全绿；Playwright 截图验证历史页选项高亮与解析展示。

## 6. 范围边界

- 不做：题目选项变更追踪（选项不可变，join 即得当时选项）、错题本独立页面、删除/清空历史。
