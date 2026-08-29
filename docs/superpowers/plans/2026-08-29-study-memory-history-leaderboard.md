# Plan：看背按钮修复 + 听学进度记忆 + 看/听历史 + 合并排行榜

基于 Spec（2026-08-29-study-memory-history-leaderboard）的任务分解。

## Task 1：后端接口（backend）

**文件**：`backend/app/service.py`、`backend/app/routers/reviews.py`、`backend/app/routers/plans.py`、`backend/tests/test_reviews.py`（新增）

- [ ] `service._entry_dict` 复用；新增 `service.entry_by_id(conn, entry_id)`（公开包装）
- [ ] `GET /api/entries/{entry_id}`：单条 Entry 或空
- [ ] `service.review_history(conn, limit, mode)`：reviews JOIN entries，按 ts 倒序
- [ ] `GET /api/reviews/history`
- [ ] `service.leaderboard(conn, limit, sort)`：按条目聚合 read/listen/total/repeat/last_ts
- [ ] `GET /api/leaderboard`
- [ ] `_listen_pool` 返回条目附 `listen_count` / `last_ts`；`listen_queue`/`listen_more` 透出，并返回 `heard`
- [ ] 单测：history 过滤与排序、leaderboard 聚合口径、entries 深链、listen heard 标记

## Task 2：看背按钮修复（frontend）

**文件**：`frontend/src/components/FlashcardView.tsx`、`frontend/src/app/globals.css`、`frontend/src/lib/types.ts`

- [ ] `rate()`：submitting 状态 + try/catch + 可见错误提示（不静默）
- [ ] 卡片 pointer-events 防护 CSS（未翻转背面不命中；翻转后仅背面可交互）
- [ ] 看背卡片显示已看次数（review count）
- [ ] 支持 `?entry=ID` 深链：取该条目并置于队列首位

## Task 3：听学进度记忆（frontend）

**文件**：`frontend/src/components/ListenView.tsx`、`frontend/src/lib/types.ts`

- [ ] 队列条目展示「已听」角标与最近听过时间
- [ ] localStorage 持久化（队列 id 数组 + idx + 日期）；刷新恢复位置，队列不匹配时回退未听第一条
- [ ] 进度文案：继续第 N / 未听 X · 已听 Y
- [ ] 「跳过」写 reviews（exposed）；暂停 ≥15s 写 reviews（exposed）
- [ ] 支持 `?entry=ID` 深链：目标条目置首

## Task 4：历史 + 排行榜页面（frontend）

**文件**：`frontend/src/app/report/page.tsx`、`frontend/src/components/HistoryView.tsx`（新增）、`frontend/src/components/LeaderboardView.tsx`（新增）、`frontend/src/lib/types.ts`、`frontend/src/app/globals.css`

- [ ] 报告页 segments：复盘 / 覆盖 / 历史 / 排行
- [ ] HistoryView：按天分组卡片（模式徽标、结果、时长、时间）+ 「再看/再听」深链
- [ ] LeaderboardView：全部/只看/只听过滤 + 排序切换；合计、重复次数；「继续看/继续听」深链
- [ ] types.ts 增加 HistoryItem / LeaderboardItem / 深链参数类型

## Task 5：测试与回归

**文件**：`backend/tests/test_reviews.py`、`frontend/src/components/*`

- [ ] `pytest` 全绿（新增用例 + 存量回归）
- [ ] Playwright：看背评分流程、听学刷新恢复、历史页、排行榜页、深链跳转
- [ ] 代码行数自查（< 300/组件、< 500 文件硬上限）

## Task 6：看背进度记忆（2026-08-30 补充）

**文件**：`backend/app/service.py`、`backend/tests/test_reviews.py`、`frontend/src/components/FlashcardView.tsx`、`frontend/src/lib/types.ts`

- [ ] `service._attach_reviewed_today(conn, items, day)`：批量标记今日已看
- [ ] `plan_payload` / `continue_plan_entries` / `custom_entries` 三处接入
- [ ] FlashcardView：localStorage 队列位置恢复（公共前缀回退）
- [ ] 「今日已看」徽标 + 进度行「今日已完成 T 条」+ 评分后即时累加
- [ ] 单测：review 后 plan 条目 `reviewed_today=True`
- [ ] Playwright：刷新恢复位置、已看标记、继续后刷新回退计划末尾

## 执行顺序

Task 1 → 2 → 3 → 4 → 5 → 6；完成后用户确认再提交（git commit 需用户明确同意）。
