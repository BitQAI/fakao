# Plan：看背/听学自定义范围模式

基于 Spec（2026-08-29-custom-study-range）的任务分解。

## Task 1：后端自定义范围（service + 路由）

**文件**：`backend/app/service.py`、`backend/app/routers/plans.py`

- [ ] `service.custom_entries(conn, subjects, points, limit, listen_only)`：并集过滤 + 优先级/科目排序 + 上限
- [ ] `POST /api/plans/custom`、`POST /api/listen/custom` 路由（复用 CustomRangeIn schema）

## Task 2：自定义范围选择器（前端共享组件）

**文件**：`frontend/src/components/CustomRangePicker.tsx`（新增）、`frontend/src/app/globals.css`

- [ ] 模式选择（按科目 / 按知识点）
- [ ] 科目多选列表（带条数）
- [ ] 知识点三级树（折叠、父级全选/半选联动、TriCheck 组件）
- [ ] 底部确认/返回/取消；复用 `.source-modal/.source-panel` 弹窗样式

## Task 3：看背接入

**文件**：`frontend/src/components/FlashcardView.tsx`

- [ ] 顶部「自定义范围」按钮 + 自定义确认调 `/api/plans/custom` 替换队列
- [ ] 自定义模式学完视图：「自定义范围已学完」+「重新选择范围」
- [ ] 空范围提示

## Task 4：听学接入

**文件**：`frontend/src/components/ListenView.tsx`、`frontend/src/lib/types.ts`

- [ ] `ListenPayload` 增加 `custom?: boolean`
- [ ] 顶部「自定义范围」按钮 + 确认调 `/api/listen/custom`
- [ ] 自定义模式学完视图与空范围提示

## Task 5：测试与回归

**文件**：`backend/tests/test_quiz_continue.py`

- [ ] 按科目/按知识点过滤用例、听学可听过滤用例、空选择用例
- [ ] `pytest` 全绿
- [ ] Playwright：看背与听学的自定义流程截图验证

## 执行顺序

Task 1 → 2 → 3 → 4 → 5；完成后用户确认再提交。
