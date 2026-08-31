# Plan：看背导航 / 听背标记 / 自定义范围续学与已学状态展示

- 日期：2026-08-31
- 上游 Spec：`docs/superpowers/specs/2026-08-31-study-nav-marks-continue.md`
- 涉及模块：backend（service / routers/plans）、frontend（FlashcardView / ListenView / CustomRangePicker / progressStore / globals.css）、tests

## Task 1：后端 custom 接口支持 exclude + total/remaining

- 文件：
  - `backend/app/routers/plans.py`
  - `backend/app/service.py`
  - `backend/tests/test_quiz_continue.py`
- 接口定义：
  - `CustomRangeIn` 新增 `exclude: list[str] = []`；
  - `service.custom_entries(conn, subjects, points, listen_only=False, exclude=None) -> list[dict]`：返回全量排序列表，过滤条件改为 `AND (subjects OR points) AND tts_text!=? AND id NOT IN (exclude)`；
  - 路由切片：`plans/custom` → `{items: items[:limit], total: len(items)}`；`listen/custom` → `{items: items[:min(limit,100)], remaining: len(items), ...}`。
- 测试：
  - [ ] `test_custom_plan_excludes`：exclude 后只返回未排除条目
  - [ ] `test_custom_plan_total`：total 为范围全量
  - [ ] `test_custom_listen_remaining_excludes`：remaining 为排除后剩余
  - [ ] 既有 custom 用例全部保持通过

## Task 2：FlashcardView 返回上一条 + 自定义续学

- 文件：`frontend/src/components/FlashcardView.tsx`
- 改动：
  - [ ] 新增状态 `customRange / seenIds / remaining`
  - [ ] `applyCustom` 支持 `{exclude, limit}`，响应读取 `total`，维护 seenIds 与 remaining
  - [ ] 学完视图（customMode）：显示剩余未学条数；「下一组 20 / 50 / 自定义数量」续学按钮；无剩余时提示已全部学完
  - [ ] 卡片下方新增「上一个 / 下一个」导航（重置翻转与计时，首条禁用上一个）

## Task 3：ListenView 标记 + 自定义续学

- 文件：`frontend/src/lib/progressStore.ts`、`frontend/src/components/ListenView.tsx`
- 改动：
  - [ ] progressStore 新增 `MarkedItem` 类型与 read/write/toggle 辅助函数
  - [ ] ListenView 加载/写入标记，当前卡片「标记 / 已标记」切换 + 徽标
  - [ ] 「已标记（N）」弹层：列表、重背（队列内跳转/取回插队+强制重载音频）、查看（跳转看背深链）、取消标记、清空
  - [ ] 新增 `customRange / seenIds / remaining`，`applyCustom` 支持排除续学
  - [ ] 自定义学完视图新增「继续听剩余」区（20/50/自定义数量）

## Task 4：CustomRangePicker 已学/未学标识与数量

- 文件：`frontend/src/components/CustomRangePicker.tsx`、`frontend/src/app/globals.css`
- 改动：
  - [ ] 按科目模式：科目行显示「已学 A · 未学 B」
  - [ ] 按知识点模式：科目/子科目行显示数量；知识点行显示状态徽标（未学/已学/薄弱）
  - [ ] 新增 `.pick-state` 等少量样式

## Task 5：验证

- [ ] `backend/.venv/bin/python -m pytest tests`（新增 3 个用例 + 回归）
- [ ] `frontend`：`npx tsc --noEmit`
- [ ] 启动 backend(:8090) + frontend(:3001)，浏览器冒烟验证四项需求
- [ ] 汇总结果，commit 前先向用户确认
