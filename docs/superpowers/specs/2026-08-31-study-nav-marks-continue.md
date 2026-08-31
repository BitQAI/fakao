# Spec：看背导航 / 听背标记 / 自定义范围续学与已学状态展示

- 日期：2026-08-31
- 状态：待评审
- 涉及模块：frontend（FlashcardView / ListenView / CustomRangePicker / progressStore / types / globals.css）、backend（service / routers/plans）、tests

## 1. 问题背景

现有看背/听学/自定义范围的使用痛点：

1. 看背只能通过评分前进，看错了想回看上一条只能重进页面；
2. 听学时听到重点只能重听当前段，无法把「想再背的条目」收藏起来集中重背；
3. 自定义范围默认一次最多取 200 条，学完后只有「重新选择范围」，无法继续学同范围内剩余未学条目；
4. 自定义范围选择器只显示条目总数，看不到哪些已学、哪些未学，选范围时无法避开已掌握内容。

## 2. 方案概要

### 2.1 看背返回上一条（纯前端）

- FlashcardView 卡片下方增加「上一个 / 下一个」导航行：
  - 上一个：`index-1`，重置翻转状态与计时起点；首条禁用；
  - 下一个：`index+1`（不评分、不记暴露），与听学「下一段」行为对齐。
- 队列位置照常持久化到 localStorage（复用 `writeSavedQueue`）。

### 2.2 听背标记（纯前端，localStorage）

- 新增本地存储 `fakao.listen.marked.v1`，结构为 `{id, subject, point, ts}[]`，与现有队列记忆同模块（`progressStore.ts`）。
- 听学卡片上提供「标记 / 已标记」切换按钮，当前条目已标记时卡片显示徽标。
- 页面顶部新增「已标记（N）」入口，打开底部弹层：
  - 列出所有已标记条目（科目 + 考点）；
  - 每条提供「重背」：若条目在当前队列中则跳到该段播放，否则取回条目并插入队首播放（强制重载音频）；
  - 「查看」：跳转 `/study?view=read&entry=<id>` 查看卡片结论/法条/案例；
  - 支持单条取消标记与清空全部。

### 2.3 自定义范围学完 → 继续剩余下一组/部分

- 后端：
  - `POST /api/plans/custom` 与 `POST /api/listen/custom` 请求体新增 `exclude: string[]`；
  - 两个接口响应分别新增 `total`（范围过滤+排除后的总条数）与语义化的 `remaining`（范围过滤+排除后的剩余可听条数，不再等于返回条数）；
  - 排序保持「优先级 × 科目顺序 × id」，切片逻辑移到路由层（`custom_entries` 返回全量排序列表）。
- 前端：
  - 记录当前自定义范围（subjects/points）与已加载条目 id 集合（seenIds）；
  - 学完视图在「重新选择范围」之外新增续学区：显示「剩余未学 X 条」，「下一组 20 / 下一组 50 / 自定义数量」按钮，带 `exclude=seenIds` 请求下一批；
  - 无剩余时提示「所选范围已全部学完」。

### 2.4 自定义范围已学/未学标识与数量（纯前端）

- 复用 `GET /api/coverage` 各节点 `states`（new / learned / weak / mastered）：
  - 按科目模式：科目行显示「已学 A · 未学 B」；
  - 按知识点模式：科目行/子科目行显示同款数量，知识点行显示状态徽标（未学 / 已学 / 薄弱）。

## 3. 数据模型

无表结构变更。学习记录照常写入 `reviews`；标记仅存浏览器 localStorage（个人设备级，不上传）。

## 4. API 定义

### `POST /api/plans/custom`

```json
{"subjects": ["刑法"], "points": [], "limit": 200, "exclude": ["XF-001"]}
→ {"items": [Entry...], "total": 42}
```

### `POST /api/listen/custom`

```json
{"subjects": [], "points": ["正当防卫限度"], "limit": 100, "exclude": ["XF-002"]}
→ {"items": [Entry...], "remaining": 3, "generating": false, "custom": true}
```

`exclude` 为空数组时行为与现状完全一致。

## 5. 验证标准

1. pytest：custom 接口排除后结果正确、total/remaining 语义正确、空 exclude 回归不破坏现有用例；
2. 前端 `tsc --noEmit` / `next build` 通过；
3. 浏览器冒烟：看背上一个/下一个可切换；听学标记后弹层可重背、可查看；自定义学完出现续学按钮且排除已学；选择器显示已学/未学数量。

## 6. 范围边界

- 不做：标记云同步/后端持久化；标记队列排序自定义；自定义范围会话持久化（刷新后需重选）；与今日计划合并。
