# Plan：前端阅读体验修复 + 自测多选/解析 + 看背听背续学

基于 Spec（2026-08-29-frontend-ux-quiz-continue）的任务分解。

## Task 1：markdown 渲染器升级（frontend/src/lib/md.ts + globals.css）

**文件**：`frontend/src/lib/md.ts`、`frontend/src/app/globals.css`

**内容**：
- [ ] `mdToHtml`：先 HTML 转义 → 行级处理（`#~###`、`-`/`1.` 列表、`|` 表格、`>` 引用、`---`、段落）→ 行内处理（`**`、`*`、`` ` ``）→ 段落内单换行 `<br/>`
- [ ] `globals.css`：`.report-content` 补充 `p/ul/ol/li/strong/em/code/blockquote/table/th/td/hr` 样式；段落间距、表格边框

## Task 2：看背卡片布局修复（FlashcardView + globals.css）

**文件**：`frontend/src/components/FlashcardView.tsx`、`frontend/src/app/globals.css`

**内容**：
- [ ] `.flashcard-inner` 改 Grid 单格堆叠，容器高度随内容增长；背面 `justify-content` 移除
- [ ] 案例 chips 改整行圆角条目样式（`.chip-case`），支持 2 行截断；法条 chips 间距加大
- [ ] 评分行与卡片间距，消除重叠

## Task 3：SourceViewer 渲染 + 法条款/项解析修复

**文件**：`frontend/src/components/SourceViewer.tsx`、`frontend/src/app/globals.css`、`backend/app/statutes.py`、`backend/app/routers/source.py`

**内容**：
- [ ] `_ARTICLE_RE` 允许条号后 `第N款/项/目` 后缀；`resolve_statute` 忽略后缀取整条
- [ ] `/api/statute` 改 `resolve_statute(f"{law}{no}")`，不再补「条」
- [ ] SourceViewer 正文改 `dangerouslySetInnerHTML` + `mdToHtml`（案例 markdown 标题/分段生效）；`.source-text` 样式更新

## Task 4：自测多选 + 解析（后端）

**文件**：`backend/app/db.py`、`backend/app/ai.py`、`backend/app/service.py`、`backend/app/routers/quizzes.py`

**内容**：
- [ ] `quizzes` 表加 `analysis` 列（SCHEMA_SQL + 启动迁移）
- [ ] `ai.generate_quiz`：prompt 支持多选（约 1/3）与 `analysis` 字段；校验
- [ ] `service.build_daily_quiz`：缓存命中带 `analysis`；空则惰性生成并落库；cloze 兜底解析=结论
- [ ] `routers/quizzes.py`：判题归一化（排序/去重/大写）；响应带 `analysis`

## Task 5：自测多选 + 解析（前端）

**文件**：`frontend/src/components/QuizView.tsx`、`frontend/src/app/globals.css`

**内容**：
- [ ] `answer.length>1` 判定多选：方形复选框 + 「提交答案」按钮；单选保持点选即答
- [ ] 提交后：正确选项绿框、误选红框、展示正确答案与解析（`mdToHtml` 渲染）
- [ ] 多选选项样式 `.option.multi` 与 `.option-check` 复选框

## Task 6：看背/听背续学（后端）

**文件**：`backend/app/service.py`、`backend/app/routers/plans.py`、`backend/app/routers/audio.py`（或新增路由）

**内容**：
- [ ] `service.continue_plan_entries(conn, count)`：排除今日计划，按桶序+优先级取 N
- [ ] `service.listen_more(conn, exclude_ids, count)`：听学池排序，排除已含
- [ ] 路由：`POST /api/plans/continue`、`POST /api/listen/more`
- [ ] 单元测试：排序、排除、边界

## Task 7：看背/听背续学（前端）

**文件**：`frontend/src/components/FlashcardView.tsx`、`frontend/src/components/ListenView.tsx`

**内容**：
- [ ] 看背学完页：显示「继续学 5 / 10 / 自定义(输入)」按钮；追加条目继续刷并记录评分
- [ ] 听背学完：不跳回第一段，显示「再听 5 / 10 / 自定义」；追加队列继续播
- [ ] 自定义数量输入校验（1~50）

## Task 8：测试与回归

**文件**：`backend/tests/test_service.py`、`backend/tests/test_api.py`、`backend/tests/test_ai.py`、`backend/tests/test_statutes.py`（新增）

**内容**：
- [ ] 法条款/项解析用例（刑法20条第3款、刑诉法200条第3项）
- [ ] 多选判题归一化用例（"BA" == "AB"）
- [ ] analysis 落库与返回用例
- [ ] 续学接口用例
- [ ] `pytest tests` 全绿
- [ ] Playwright 截图回归：翻卡背面、法条款/项弹窗、案例弹窗、报告、多选答题+解析、续学入口

## 执行顺序

Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8（后端与前端任务可并行验证，最终统一回归）。

每个 Task 完成后不单独 commit；全部完成、用户确认后按 `type(scope): description` 一次或分次提交。
