# Spec：看背/听学自定义范围模式（按科目 / 按知识点）

- 日期：2026-08-29
- 状态：待评审
- 涉及模块：backend（service / routers/plans）、frontend（新组件 CustomRangePicker / FlashcardView / ListenView / types.ts / globals.css）、tests

## 1. 问题背景

看背只能按系统调度计划（今日 plan）学习，听学只能按听学池（未听优先）顺序播放。用户希望**自主选择学习范围**：

1. 按科目：选择 1 个或多个科目，学习该科目全部条目；
2. 按知识点：像「覆盖」页一样展示 科目 → 子科目 → 知识点 树，勾选想学的知识点。

## 2. 方案概要

### 2.1 选择器（前端共享组件）

- 新增 `CustomRangePicker` 底部弹窗（看背/听学共用）：
  - 第一步选模式：**按科目选择** / **按知识点选择**；
  - 按科目：8 科多选 checkbox（显示各科条目数）；
  - 按知识点：三级树（科目可折叠、科目/子科目 checkbox 全选与半选联动、知识点 checkbox 多选），数据源复用 `GET /api/coverage`；
  - 底部「开始学习（N）」确认。

### 2.2 后端接口

- `POST /api/plans/custom {subjects, points, limit=200}` → `{items: Entry[]}`（看背）
- `POST /api/listen/custom {subjects, points, limit=100}` → `{items, remaining, generating, custom:true}`（听学，仅返回 `tts_text != ''` 条目）
- 过滤：subjects 与 points 为并集（一次只启用一种模式）；排序：优先级 × 科目顺序 × id；上限保护。
- 学完视图区分：自定义模式显示「自定义范围已学完」+「重新选择范围」，不再出现默认计划的「继续 5/10/自定义」。

### 2.3 数据模型

无表结构变更；学习记录照常写入 `reviews`（看背 good/fuzzy/bad、听学 exposed）。

## 3. API 定义

### `POST /api/plans/custom`

```json
{"subjects": ["刑法"], "points": [], "limit": 200}
→ {"items": [Entry...]}
```

### `POST /api/listen/custom`

```json
{"subjects": [], "points": ["正当防卫限度"], "limit": 100}
→ {"items": [Entry...], "remaining": N, "generating": false, "custom": true}
```

## 4. 验证标准

1. pytest：按科目过滤、按知识点过滤、听学仅含可听条目、空选择返回空；
2. Playwright：看背进入自定义 → 按科目选「刑法」→ 卡片切换为刑法条目；按知识点勾选 → 队列为对应知识点；学完后出现「重新选择范围」；听学同样验证。

## 5. 范围边界

- 不做：自定义范围持久化（每次进入重新选）、与今日计划合并、自定义数量上限 UI（后端上限即保护）。
