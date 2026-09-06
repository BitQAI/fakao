# 听学/AI/看背 5 项优化 Spec（2026-09-06）

## 背景
- 听学一次拉 100 条（含 tts_text 大字段），首屏慢、音频断流感强。
- 听学只播音频，看不到条目全文。
- AI 问答入口只有看背卡片，且无标题/描述快捷填入；问过无痕，下次遇到同条目不知道有历史。
- 看背发现条目错误无法就地更正。

用户确认：预加载 10 条剩 3 自动续 10；原文看全文；AI 按看背条目维度；编辑仅文本字段。

## 方案概要
1. **听学预加载 10/剩3**：`GET /api/listen?limit=10` 首屏 10 条；前端 `idx >= len-3` 且 `remaining>0` 时后台静默取下 10 条追加（普通走 `/api/listen/more`，自定义走 `/api/listen/custom`），另预热下 1 条音频（`new Audio().preload='auto'`，只 1 条省流量）。
   - 为何不用其他方案：整队 ID+懒取详情首屏最快但要新增批量接口、改动大；滑动窗口丢已播破坏“上一个”回看；15/5 与 10/3 体验接近，10/3 首屏更快、续取更频繁但单次更轻，TTS 音频是真正瓶颈故叠加 1 条音频预热即可。
2. **听学原文展示**：听学卡片加“显示原文/收起”折叠区，展示 point/anchor/conclusion/note/tts_text + statutes chips + cases chips，复用 SourceViewer（需补 statute 透传）。
3. **AI 快速复制标题与描述**：`ask-ai` 事件 detail 扩展 `title/description`；AiChat 顶部快捷行“填入标题/填入描述/复制问法”，走 clipboard+input 填入，不自动发送。
4. **AI 历史徽标**：后端已写 chat_logs（related_entry_ids），新增 `GET /api/assistant/history?entry_id=`（Python 侧 JSON 解析过滤，避免 LIKE 误配 `XF-001`/`XF-0010`）；Flashcard 卡片显示“问过AI·N条”，AiChat 内可展开历史问答，点击回填问题。
5. **看背条目编辑**：新增 `PUT /api/entries/{id}`，仅允许 point/anchor/conclusion/note/priority（不碰 tts/音频/status）；校验对齐 importer（anchor 16–36 字、conclusion ≤60 且以“。”结尾、priority 枚举、point 非空）；前端卡片背面加“编辑”按钮弹层表单，就地更新队列。

## 技术选型
- 后端：FastAPI + SQLite，现成 `service/record_chat` 复用；历史查询 Python 侧过滤（量小，无需 json_each 依赖）。
- 前端：沿用 `fetch` + `source-modal` 弹层 + 现有 btn/chip 样式，不引新依赖。

## 数据模型
- 无新表。entries 原地 UPDATE（final 状态不变）；chat_logs 只读查询。

## API 设计
- `GET /api/listen?limit=10`（默认 10，上限 50，向后兼容不传即 10？为兼容旧缓存默认 100→改为默认 10，前端显式传 limit=10）
- `GET /api/assistant/history?entry_id=XXX&limit=20` → `{items:[{id,ts,question,answer,related_entry_ids}]}`
- `PUT /api/entries/{id}` body `{point,anchor,conclusion,note,priority}` → 更新后 entry（含计数）

## 验证标准
- `backend/.venv/bin/python -m pytest tests` 全过（含新增：listen limit、history 过滤、entry 更新校验）。
- 前端 `npm run build`（或 tsc）通过；听学翻到剩 3 条时网络面板出现一次续取且 idx 不跳；原文折叠/编辑弹层可用。

## 范围边界
- 不做：自测题维度 AI、音频重合成、条目法条/案例结构编辑、滑动窗口丢队列、ID 列表懒加载。
- 已知局限：刷新后听学队列若顺序变化则从头播（分页后精确恢复需批量取接口，本次不做）。
