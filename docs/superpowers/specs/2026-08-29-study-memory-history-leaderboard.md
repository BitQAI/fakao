# Spec：看背按钮修复 + 听学进度记忆 + 看/听历史 + 合并排行榜

- 日期：2026-08-29
- 状态：待评审
- 涉及模块：backend（service / routers / tests）、frontend（FlashcardView / ListenView / report 页 / types / globals.css）

## 1. 问题背景

用户反馈四个问题（按严重度排序）：

1. **看背按钮没反应**：看背评分（没记住/模糊/记住了）、自定义范围等按钮存在无响应现象。
2. **听学没有记忆**：听学队列 100 条听到 65 条，刷新页面后又从头开始；已听/未听无任何区分。
3. **看背/听学没有历史**：听完了、背完了不知道哪些听过/背过。
4. **没有排行榜**：希望看与听合并统计，能看到重复听/看的次数，并能快速索引到条目继续学习。

## 2. 现状分析（已实测复现）

### 2.1 看背按钮

`FlashcardView.rate()` 是 async 且**无 try/catch、无 loading 态**：`postJson("/api/reviews")` 一旦失败（后端抖动、超时），Promise rejection 无人处理，`setIndex` 不执行 → UI 停在原卡片，表现为"按钮没反应"。

卡片翻转用 `rotateY(180deg) + backface-visibility: hidden`，背面按钮（法条/案例/问 AI）位于 3D 变换容器内；部分移动浏览器（尤其 iOS Safari）在 `backface-visibility: hidden` 状态下仍会拦截命中，点击可能被吞。

### 2.2 听学

实测（Playwright）：听 `XF-163` → 点「下一段」跳过 → `MF-082` → 刷新页面 → 回到 `XF-163`。

原因：
- 「跳过」不写 `reviews`（只有 `onEnded` 才记录，暂停/跳过错失）；
- 队列 `GET /api/listen` 每次重新生成，无位置记忆；
- 队列排序是"未听优先"，刷新后未听条目（可能含用户已跳过的）重新排到最前，且 UI 不区分已听/未听，用户感知"从头开始"。

### 2.3 历史与排行榜

`reviews` 表已完整记录每次看/听（mode、result、duration_sec、ts），`quiz_answers` 已有历史页先例；看/听历史与排行榜**纯查询即可，无需表结构变更**。

## 3. 方案概要

### 3.1 看背按钮加固（防御性修复 + 错误可见化）

- `rate()` 增加 submitting 状态：点击后按钮禁用，POST 失败时显示错误提示而非静默卡死。
- CSS `pointer-events` 防护：未翻转时 `.flashcard-face.back` 不接收指针事件；翻转后仅背面可交互，杜绝 3D 变换命中异常。
- 卡片正面点击翻转逻辑保留，按钮 `stopPropagation` 已有，再补 `onClick` 显式判定，避免误触。
- 看背卡片显示该条已看次数（与历史联动，用户能立刻知道"背过几次"）。

### 3.2 听学进度记忆

**数据**：复用 `reviews`（listen 记录即"已听"事实）。

**后端**：
- `GET /api/listen` / `POST /api/listen/more` 返回每个条目附 `listen_count`、`last_ts`（已听标记），并返回 `heard_total`（累计已听条数）供前端展示进度。
- 队列排序保持"未听优先 → 已听按最近听过时间降序"，刷新后未听部分自然衔接。
- 新增 `GET /api/entries/{id}`：供深链"继续学/继续听"取单条条目。

**前端**：
- 队列位置持久化到 localStorage（存队列条目 id 数组 + 当前 idx + 日期）：刷新时若队列仍匹配则恢复原位，否则回退到第一个未听条目。
- 顶部进度文案：`继续第 N / 未听 X · 已听 Y`，已听条目带「已听」角标。
- 「跳过」与「暂停 ≥15 秒」也写 `reviews`（mode=listen, result=exposed），保证"听过就算"。
- 支持 `?entry=ID` 深链：队列 = [目标条目] + 常规队列（去重），定位到目标条目。

### 3.3 看/听历史

- 新接口 `GET /api/reviews/history?limit=100&mode=read|listen`：`reviews JOIN entries` 返回时间、模式、结果、时长、条目（含 point/subject/anchor/conclusion）。
- 前端：报告页新增「历史」segment，按天分组展示看/听记录，每条含「再看 / 再听」快捷按钮（深链）。

### 3.4 合并排行榜

- 新接口 `GET /api/leaderboard?limit=200&sort=total|read|listen`：按条目聚合 `read_count`、`listen_count`、`total_count`、`last_ts`，JOIN entries 返回完整条目信息。
- 前端：报告页新增「排行」segment：
  - 默认按总次数倒序；提供「全部 / 只看 / 只听」过滤与排序切换。
  - 每条显示科目 · 考点、看 N 次 / 听 N 次 / 合计、重复次数（= 总次数 - 去重数，即 count-1 口径直接展示为"重复听 N 次 / 重复看 N 次"）。
  - 「继续看」「继续听」按钮 → `/study?view=read&entry=ID`、`/study?view=listen&entry=ID`。

### 3.5 页面入口

- 报告页 segments 扩为：复盘 / 覆盖 / 历史 / 排行（BottomNav 不动，入口集中）。
- 备选方案：放入学习页或新增底部 tab；移动端底部 5 tab 拥挤、学习页 segment 已达 3 个，故选报告页。

### 3.6 看背进度记忆（2026-08-30 补充）

- 与听学同构：`FlashcardView` 用 localStorage 持久化队列条目 id 数组 + 当前 idx（key `fakao.read.queue.v1`）。
- 恢复规则：刷新后取**公共前缀**匹配——今日计划不变时精确恢复位置；「继续」追加的条目刷新后不存在时回退到计划末尾（公共前缀长度）；跨天/计划变化无公共前缀则从第 1 条开始。
- 今日已看标记：`plan_payload` / `continue_plan_entries` / `custom_entries` 每条目返回 `reviewed_today`（当天是否有 `mode='read'` 记录），卡片标题显示「今日已看」徽标。
- 进度行：`第 N / M · 完成 D 张 · 今日已完成 T 条`（T = 后端标记 + 本次会话新评分即时累加）。
- 深链 `?entry=ID` 已有（目标置首），不参与位置恢复。

## 4. 数据模型

无变更。全部复用现有 `reviews` / `entries` 表。

## 5. API 设计

### `GET /api/reviews/history?limit=100&mode=`

```json
{"items": [{
  "id": 123, "entry_id": "XF-001", "ts": "2026-08-29T19:54:29",
  "mode": "listen", "result": "exposed", "duration_sec": 16,
  "entry": {"id": "XF-001", "subject": "刑法", "point": "...", "anchor": "...", "conclusion": "...", "priority": "高频考点"}
}]}
```

### `GET /api/leaderboard?limit=200&sort=total`

```json
{"items": [{
  "entry_id": "XF-001", "subject": "刑法", "submodule": "分则-财产犯罪",
  "point": "转化型抢劫", "anchor": "...", "conclusion": "...",
  "priority": "高频考点",
  "read_count": 3, "listen_count": 5, "total_count": 8,
  "read_repeat": 2, "listen_repeat": 4, "last_ts": "2026-08-29T19:54:29"
}]}
```

### `GET /api/entries/{entry_id}`

返回单条 `Entry`（含 sources/cases/statutes/tts_text），404 时返回空。

## 6. 验证标准

1. 看背：评分按钮点击后正常翻页；POST 失败时有可见错误提示；翻卡片与按钮点击互不干扰。
2. 听学：听 3 条（含跳过 1 条）→ 刷新 → 恢复位置且继续到未听条目；已听条目有角标；跳过项也计入已听。
3. 历史：看/听记录按天分组展示，能跳转到对应条目。
4. 排行榜：总数 = 看 + 听；重复次数正确；「继续看/听」能定位到目标条目。
5. `pytest` 全绿；Playwright 覆盖以上主流程。

## 7. 范围边界

- 不做：多用户账号体系（本工具单机单用户）、跨设备进度同步、删除/清空历史、听学按条目级播放进度（当前按"已听/未听"）。
- 不做：排行榜分页（上限 200 足够）；不做 quiz 并入排行榜（用户明确是看与听）。
