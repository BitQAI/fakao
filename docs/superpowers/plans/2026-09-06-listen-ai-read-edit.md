# 实施计划：听学/AI/看背 5 项（2026-09-06）

输入：`docs/superpowers/specs/2026-09-06-listen-ai-read-edit.md`

## Task 1 — 后端：listen 分页 + 历史 + 条目编辑
- 文件：`backend/app/service.py`（`listen_queue(limit)`、`chat_history_for_entry`、`update_entry_text`）、`backend/app/routers/plans.py`（`GET /listen?limit`、`PUT /entries/{id}`）、`backend/app/routers/assistant.py`（`GET /assistant/history`）
- 接口定义见 Spec §API 设计；校验对齐 `importer.py`（ANCHOR 16–36、CONCLUSION ≤60+“。”、PRIORITY 枚举）
- [ ] `listen_queue(conn, limit=10)` 切片并保留 heard_total/remaining
- [ ] `GET /api/assistant/history` Python 侧 json 过滤 related_entry_ids
- [ ] `PUT /api/entries/{id}` 仅 5 字段 + 校验 + 返回 `entry_by_id`
- [ ] pytest 新增/更新用例并全过

## Task 2 — 前端：听学 10/剩3 预加载 + 原文展示
- 文件：`frontend/src/lib/listenInit.ts`（首屏 limit=10）、`frontend/src/components/ListenView.tsx`（阈值自动续取 + 音频预热 1 条 + 原文折叠区 + statute 透传）
- [ ] 普通/自定义双通道静默续取（`prefetching` 独立状态、防重入、失败只写 notice）
- [ ] 音频预热下 1 条；原文折叠默认收起，展开含全文+chips
- [ ] 不跳 idx：续取只追加；自定义同步 seenIds/remaining

## Task 3 — 前端：AI 快捷填入 + 历史徽标
- 文件：`frontend/src/components/AiFab.tsx`（prefill 扩展）、`AiChat.tsx`（快捷行+历史列表）、`FlashcardView.tsx`（dispatch title/desc、徽标、编辑弹层见 Task 4）
- [ ] `ask-ai` detail 含 title/description；AiChat 缺失时按 entry_id 回查
- [ ] Flashcard 按 entry 取历史计数并缓存，显示“问过AI·N”
- [ ] AiChat 内历史可展开、点击回填 input

## Task 4 — 前端：看背条目编辑弹层
- 文件：`frontend/src/components/FlashcardView.tsx`（编辑按钮+表单弹层，就地更新 plan.items）
- [ ] 字段：point/anchor/conclusion/priority/note；客户端长度提示 + 服务端错误展示
- [ ] 保存成功就地更新当前 entry，不重置 index/done

## Task 5 — 验证
- [ ] `backend/.venv/bin/python -m pytest tests -q`
- [ ] 前端 `npm run build` 或 `tsc --noEmit`（以仓库实际脚本为准）
- [ ] 手工：听学续取一次、原文展开、AI 快捷+历史、编辑保存
