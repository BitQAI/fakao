# Spec：前端阅读体验修复 + 自测多选/解析 + 看背听背续学

- 日期：2026-08-29
- 状态：待评审
- 涉及模块：frontend（FlashcardView / ListenView / QuizView / SourceViewer / report 页 / md.ts / globals.css）、backend（service / ai / statutes / routers/quizzes / routers/plans / routers/listen / db.py）

## 1. 问题背景

视觉自检（移动端 390×844 截图 + 代码审查）确认以下问题：

1. **看背翻卡重叠**：`.flashcard-inner` 固定 `min-height:300px` 且两面卡片 `position:absolute`，背面内容（结论+法条 chips+案例 chips+问AI按钮）超出高度时溢出，`问 AI` 按钮与下方评分按钮重叠；案例长标题被塞进窄胶囊，换行 3 行、行距极小，阅读体验差。
2. **法条打开失败**：带「款/项」的引用（`刑法第20条第3款`、`刑诉法第200条第3项`）解析后后端拼出 `刑法第20条第3款条`，`_ARTICLE_RE` 又不允许条号后跟款/项，返回 404「法条未收录」。
3. **案例正文无排版**：案例文本含 `# 指导性案例第1号` 等 markdown 标记，原样显示；`关键词/裁判要点/相关法条/基本案情` 段间无空行，长段落挤成一块。
4. **报告 markdown 未渲染**：`mdToHtml` 只处理 `##` 与 `-`，`**加粗**` 星号原样显示；`<li>` 无 `<ul>` 包裹。今日页 `plan.rationale` 同病。
5. **自测只支持单选**：UI 为圆形单选；数据层 `answer` 只允许单字母。
6. **自测无解析**：`quizzes` 表无解析字段，LLM 生成 prompt 不要求解析，答题后无任何解释。
7. **看背/听背学完无续学**：看背学完即结束；听背播完跳回第一段，无法选择继续学多少。

## 2. 方案概要

### 2.1 展示层（前端）

- **看背卡片**：改为 CSS Grid 单格堆叠两面卡片，容器高度由内容最高的一面决定（自然撑高），消除溢出重叠；背面内容改为顶部对齐留白；案例长标题从窄胶囊改为整行圆角条目（2 行截断），法条保持短胶囊。
- **SourceViewer**：案例与法条正文改用升级后的 markdown 渲染器（先转义 HTML，再渲染标题/加粗/列表/段落/表格/引用），替代 `<pre>`；段间距交给 CSS。
- **报告/今日**：`mdToHtml` 升级为完整轻量渲染器（无第三方依赖）：`#~###` 标题、`**加粗**`、`*斜体*`、`` `代码` ``、`-`/`1.` 列表、`|` 表格、`>` 引用、`---` 分隔线、段落与 `<br/>`。今日页 rationale 一并改用渲染器。
- **自测**：多选支持（`answer` 长度 >1 判定多选）：多选 UI 用方形复选框 + 「提交答案」，单选保持点选即答；答题后高亮正确/错误选项，展示对错、正确答案、解析。

### 2.2 数据/接口层（后端）

- **法条解析**：`_ARTICLE_RE` 允许条号后跟 `第N款/项/目` 等后缀；`/api/statute` 直接 `resolve_statute(f"{law}{no}")`，不再拼接多余的「条」。
- **题库**：`quizzes` 增加 `analysis TEXT NOT NULL DEFAULT ''` 列（SCHEMA_SQL 同步 + 启动时对存量库 `ALTER TABLE` 轻量迁移，本仓库无 Alembic）；LLM 生成题目时约 1/3 出多选（答案 2~3 个字母），JSON 增加 `analysis` 字段；旧缓存题无解析时惰性补生成并落库。
- **判题**：`/api/quiz/answer` 对多选答案做字母排序归一化后比对，响应返回 `analysis`。
- **续学接口**：`POST /api/plans/continue {count}` 返回今日计划外的候选条目（错题>复习>新学 排序）；`POST /api/listen/more {count}` 返回当前队列之外的下 N 条听学条目。

## 3. 数据模型变更

```sql
-- 存量库迁移（db.connect 启动时幂等执行）
ALTER TABLE quizzes ADD COLUMN analysis TEXT NOT NULL DEFAULT '';
-- 新建库 SCHEMA_SQL 同步增加该列
```

- `qtype` 的 CHECK 约束不修改（不重建表）：多选用 `answer="AB"` 多字母表达，前端按 `answer.length > 1` 判定。
- 无其他表结构变更。

## 4. API 变更

### `GET /api/statute?law=&no=`

- 行为：`no` 可带 `第N款/项` 后缀；返回整条条文正文（款/项由前端按正文渲染）。

### `GET /api/quiz/today`

- 每个 question 增加 `analysis: string`；`answer` 可为多字母（多选）。

### `POST /api/quiz/answer`

- 入参 `user_answer`：多选为去重排序后的字母串（如 `AB`）。
- 判题：单选/多选统一归一化（去空格、大写、排序、去重）后比对。
- 响应：`{correct, answer, analysis}`。

### `POST /api/plans/continue`

- 入参：`{count: int}`（1~50，默认 5）。
- 响应：`{items: Entry[]}`：排除今日计划内条目，按 retry > review > new 桶序 + priority + 科目顺序排序取前 N。

### `POST /api/listen/more`

- 入参：`{count: int}`（1~50，默认 5）。
- 响应：`{items: Entry[], remaining: int}`：排除当前队列已含 id，按听学池排序取前 N。

## 5. 验证标准

1. Playwright 截图回归：翻卡背面无重叠、案例弹窗分段清晰、法条（含款/项）可打开、报告无 `**` 原样、多选可勾选提交、解析可见、学完可续 5/10/自定义。
2. `pytest tests` 全绿（现有 125 项 + 新增用例：款/项法条解析、多选判题归一化、续学接口排序与排除、analysis 落库）。
3. 存量库启动不报错，`quizzes.analysis` 列自动补齐。

## 6. 范围边界

- 不做：AI 聊天框 markdown 渲染（保持纯文本流式）、题库重生成、样式系统重构、数据导入改动。
- 不改 `qtype` CHECK 约束（避免重建 quizzes 表破坏 quiz_answers 外键）。
