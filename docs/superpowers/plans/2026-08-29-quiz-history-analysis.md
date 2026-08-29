# Plan：自测解析必达 + 做题历史

基于 Spec（2026-08-29-quiz-history-analysis）的任务分解。

## Task 1：解析必达（backend）

**文件**：`backend/app/service.py`、`backend/app/routers/quizzes.py`

- [ ] `service.ensure_quiz_analysis(conn, quiz, persist=True)`：LLM 懒生成 + 兜底（选择题含考点结论）+ 回写
- [ ] `build_daily_quiz` 改用 `ensure_quiz_analysis`
- [ ] `/api/quiz/answer` 响应解析改用 `ensure_quiz_analysis`

## Task 2：历史接口（backend）

**文件**：`backend/app/service.py`、`backend/app/routers/quizzes.py`

- [ ] `service.quiz_history(conn, limit)`：JOIN 查询 + 选项字母→文本映射 + 解析必达
- [ ] `GET /api/quiz/history` 路由

## Task 3：历史页（frontend）

**文件**：`frontend/src/components/QuizView.tsx`、`frontend/src/lib/types.ts`、`frontend/src/app/globals.css`

- [ ] QuizView「今日 / 历史」切换
- [ ] 历史卡片：时间、题干、选项高亮（✓/✗）、正确答案、解析
- [ ] 答题结果解析的防御性兜底
- [ ] CSS：`.history-card` / `.option-mark` / `.quiz-segments`

## Task 4：测试与回归

**文件**：`backend/tests/test_quiz_continue.py`

- [ ] 历史接口用例（含 picked_texts 与解析非空）
- [ ] 存量空解析题的兜底解析用例
- [ ] `pytest` 全绿
- [ ] Playwright 截图：历史页选项高亮 + 解析展示

## 执行顺序

Task 1 → 2 → 3 → 4；完成后用户确认再提交。
