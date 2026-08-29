# 法考冲刺工具 — AI 操作指南

本文件供 AI 代理在仓库内执行维护/拓展操作时阅读。先读本文件再动代码；用户明确需求优先于本文件建议。

## 1. 项目速览

- 栈：FastAPI 后端（`backend/`）+ Next.js 前端（`frontend/`）+ SQLite（`data/fakao.db`）。
- 本机端口：后端 uvicorn `:8090`（8000/8001 被占用），前端 `npm run dev` `:3001`（`BACKEND_URL=http://127.0.0.1:8090`）；部署仍用 8000/80。
- 核心数据：
  - `entries` 表：2304 条 final（8 科：商经知/三国法/理论法/刑诉/民诉/民法/行政法/刑法），每条含 point/anchor/conclusion/priority/sources/cases/tts_text。
  - `cases` 表：4 个来源（人民法院案例库/司法部案例库/最高检指导性案例/最高法指导性案例）共 7172 条。
  - `data/audio/<id>.wav`：听学音频缓存（gitignored）。
- 关键目录：`backend/scripts/`（运维脚本）、`data/科目资料/`（条目上游来源）、`data/entries/`（条目 JSON，git 跟踪）、`data/案例库统一/`（案例 index.csv + documents/，documents 被 gitignore）、`data/法条库/`（法条原文，校验用）。

## 2. 铁律（违反会踩坑）

1. **状态机**：条目 JSON `status=draft`，导入后**必须**执行 `UPDATE entries SET status='final' WHERE status='draft'`（全库查询都过滤 `status='final'`）。听学池续批（`generator.py`）会自动提升，手动 `import_entries.py` 不会。
2. **密钥**：只放仓库根 `.env`（`DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY`），严禁进代码/提交；`.env` 已被 gitignore。
3. **音频缓存**：`data/audio/<id>.wav` 存在且非空即跳过合成；要重生成某条须先删该 wav。`TTS_SPEED=1.0` 为正常语速（0.5~2.0 可调，经 ffmpeg atempo 实现）。
4. **API 账单**：DeepSeek（条目生成）返回 `402 Insufficient Balance`、DashScope（TTS）返回 `Arrearage` 都意味着欠费，属外部阻塞，先告知用户充值再重试；操作前可用 `ai.call_llm`/直连 API 探测。
5. **案例 index.csv 合并键**：必须是 `(来源库, 定位符)`。`定位符`（如 `case_00001`）在跨来源时重复，按 loc 单键去重会丢掉上千行（曾踩坑，见 `test_import_guiding_cases.py` 回归测试）。
6. **条目 cases 上限 3 条**：importer 硬校验 `len(cases) <= 3`；追加案例前若超限需先裁剪（优先保留指导性案例）。
7. **表格型资料块**：公司法"新旧对照表"等 markdown 表格块，多块合批（batch=5）易超 token 截断 JSON 导致"输出不可解析"，**用 `--batch 2`**。
8. **提交**：任何 git commit 前必须经用户确认；message 用英文 `type(scope): description`。

## 3. 常用操作流水线（全部在 `backend/` 下执行，用 `.venv/bin/python`）

### 3.1 生成条目（按科目）

```bash
.venv/bin/python scripts/generate_entries.py --subject 行政法 --target 150
.venv/bin/python scripts/generate_entries.py --subject 商经知 --dry-run   # 看资料块统计
```

产物追加写入 `data/entries/<科目>.json`（已有条目保留、考点去重），`status=draft`。

### 3.2 定向补缺（推荐）

```bash
.venv/bin/python scripts/generate_entries.py --subject 商经知 --gaps --batch 2
```

`--gaps` 只把"未被任何条目 sources.loc 引用的资料块"喂给模型（自动剔除复习建议/口诀/速记等元信息节），比全量重跑省时省钱。`--dry-run` 可先看缺口清单。

### 3.3 导入并提升 final

```bash
.venv/bin/python scripts/import_entries.py ../data/entries/刑法.json ...   # 校验 errors=0 才算成功
.venv/bin/python -c "from app import db; c=db.connect(); print(c.execute(\"UPDATE entries SET status='final' WHERE status='draft'\").rowcount); c.commit(); c.close()"
```

### 3.4 合成音频（幂等，只补缺失）

```bash
.venv/bin/python scripts/synthesize_audio.py
.venv/bin/python scripts/synthesize_audio.py --id=XF-001   # 单条（先删旧 wav 才会重生成）
```

### 3.5 案例装载与挂接

```bash
.venv/bin/python scripts/import_guiding_cases.py   # 精选汇编 30 个指导性案例并入统一库（按 id 去重+正文增强）
.venv/bin/python scripts/load_cases.py             # JSONL → cases 表（幂等）
.venv/bin/python scripts/match_cases.py            # 普通补配（只处理 cases 为空条目）
.venv/bin/python scripts/match_cases.py --append-guiding   # 对已有 cases 条目追加指导性案例（领域门槛+上限 3）
```

挂接后必须重导 entries JSON（见 3.3）才会同步 DB。指导性案例匹配机制：条目考点词 × 案例关键词/标题粗筛 → 正文核验（专用词必须命中）→ 领域门槛（刑事→刑法/刑诉，民事/知产→民法/民诉/商经知+三国法涉外，行政/国赔→行政法）。

### 3.6 覆盖检查

```bash
.venv/bin/python scripts/generate_entries.py --subject 三国法 --gaps --dry-run
```

或代码内 `gap_blocks(subject, entries)`。注意：loc 跨标题边界时会把"已覆盖"误报为缺口（如三国法 CISG/信用证），复测需结合条目实际内容判断。

### 3.7 测试

```bash
.venv/bin/python -m pytest tests   # 当前 125 passed
```

## 4. 后续拓展条目的思路（方法论）

完整流水线：科目资料 → 按 `## / ###` 标题切知识块 → DeepSeek 提炼 12 字段 → 校验（来源摘录命中原文/法条可解析/长度）→ 导入 final → 音频 → 案例挂接 → 覆盖对照。拓展按性价比排序：

1. **补知识空间（上游）**：给 `data/科目资料/<科>/*.md` 加内容。新增科目需同时：建 `data/科目资料/<科>/`、`generate_entries.py` 的 `SUBJECT_PREFIX` 加前缀（如 行政法→XZ）、`scheduler.py` 与 `generator.py` 的 `SUBJECT_ORDER` 加入该科。目前唯一完整缺失科目是**环境资源法**（客观约 3-5 分）。
2. **真题反推（最贴"必考"，尚未做）**：拿历年真题考点与现有 point 做差集，按频次排序补——对 180 分目标性价比最高，需要真题数据源。
3. **定向补缺（中游，已实现）**：`--gaps` 只喂未被引用块；表格块用 `--batch 2`。
4. **质量校准（下游）**：priority 现为 LLM 标注，建议后续用真题频次校正；案例挂接可加 LLM 语义复核；锚点/结论人工抽检。
5. **180 分权重参考（客观题 300 分，过线 180）**：商经 58-60 / 理论法 50 / 民法 45-48 / 刑法 37-39 / 刑诉 30-33 / 民诉 30 / 行政法 25-26 / 三国法 18-20。优先级 = 权重 × 频次 × 性价比；普通类条目（当前约 8%）不必追全。

## 5. 已踩坑记录（2026-08-29 实战）

- 重导 entries JSON 会把全部行打回 `draft`，全库查询立即失效 → 必须再 promote。
- `import_guiding_cases.py` 曾按 loc 单键重写 index.csv 丢 1000+ 行 → 已改 `(来源库, 定位符)` 键并加回归测试。
- 精选汇编 30 个指导性案例 id 全部已在统一库中，合并价值在正文/关键词增强，不新增行。
- 行政法生成偶发 anchor 短于 16 字被丢弃（LLM 输出波动），重跑对应 `--gaps` 即可。
- 追加指导性案例后 240 条条目超 3 条上限被裁剪（优先保留指导性案例），原始引用可在 git 历史恢复。
- README 中 TTS 描述需以 `backend/app/config.py` 为准（qwen-tts 链 + Ethan，非 qwen3-tts-instruct-flash/Neil）。
