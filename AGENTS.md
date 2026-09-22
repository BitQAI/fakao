# 法考冲刺工具 — AI 操作指南

本文件供 AI 代理在仓库内执行维护/拓展操作时阅读。先读本文件再动代码；用户明确需求优先于本文件建议。

## 1. 项目速览

- 栈：FastAPI 后端（`backend/`）+ Next.js 前端（`frontend/`）+ SQLite（`data/fakao.db`）。
- 本机端口：后端 uvicorn `:8090`（8000/8001 被占用），前端 `npm run dev` `:3001`（`BACKEND_URL=http://127.0.0.1:8090`）；部署仍用 8000/80。
- 核心数据：
  - `entries` 表：2427 条 final（8 科：商经知劳环/三国法/理论法/刑诉/民诉/民法/行政法/刑法），每条含 point/anchor/conclusion/priority/sources/cases/tts_text。
  - 科目口径：**商经知劳环**（原「商经知」改名）= 商法 + 经济法 + 知识产权 + **劳动法与社会保障法** + **环境资源法**；条目 ID 前缀仍为 `SJ`。
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
.venv/bin/python scripts/generate_entries.py --subject 商经知劳环 --dry-run   # 看资料块统计
```

产物追加写入 `data/entries/<科目>.json`（已有条目保留、考点去重），`status=draft`。

### 3.2 定向补缺（推荐）

```bash
.venv/bin/python scripts/generate_entries.py --subject 商经知劳环 --gaps --batch 2
```

`--gaps` 只把"未被任何条目 sources.loc 引用的资料块"喂给模型（自动剔除复习建议/口诀/速记等元信息节），比全量重跑省时省钱。`--dry-run` 可先看缺口清单。

### 3.3 导入并提升 final

导入前先干跑校验（不写库，`errors=0` 才继续）；字段口径、批次清单与真题批量导入规范见
`docs/superpowers/specs/2026-09-22-条目数据格式化元数据规范.md`：

```bash
.venv/bin/python scripts/validate_entries.py ../data/entries/刑法.json ...   # 干跑，报 E/W
.venv/bin/python scripts/import_entries.py ../data/entries/刑法.json ...   # 校验 errors=0 才算成功
.venv/bin/python -c "from app import db; c=db.connect(); print(c.execute(\"UPDATE entries SET status='final' WHERE status='draft'\").rowcount); c.commit(); c.close()"
```

### 3.4 合成音频（幂等，只补缺失）

```bash
.venv/bin/python scripts/synthesize_audio.py
.venv/bin/python scripts/synthesize_audio.py --id=XF-001   # 单条（先删旧 wav 才会重生成）
```

朗读文本在合成前统一过 `app/tts_text.normalize`（去 Markdown、符号转中文词、
中文间空格归一，不改写语义）；音频台账写在 `tts_assets`（entry_id/text_hash/时长）。

质检与修复（2026-09-20 新增）：

```bash
.venv/bin/python scripts/audit_tts.py                    # 五类问题：缺失/空/陈旧/语速异常/未建档
.venv/bin/python scripts/audit_tts.py --report ../docs/superpowers/research/2026-09-20-TTS质检报告.md
.venv/bin/python scripts/repair_tts.py                   # dry-run，列出待修复
.venv/bin/python scripts/repair_tts.py --apply           # 重合成（先取到新音频才覆盖，不会失声）
.venv/bin/python scripts/repair_tts.py --apply --backfill  # 只给健康音频补台账
```

判定口径：语速 <3.0 或 >6.5 字/秒为异常（实测中位 4.81 字/秒，>6.5 都是被截断的录音）；
整体 RMS <60 视为无声；首/尾静音 >2 秒为异常。**文本改过而音频没重合成 = 陈旧**，看 `tts_assets`。

### 3.5 案例装载与挂接

```bash
.venv/bin/python scripts/import_guiding_cases.py   # 精选汇编 30 个指导性案例并入统一库（按 id 去重+正文增强）
.venv/bin/python scripts/load_cases.py             # JSONL → cases 表（幂等）
.venv/bin/python scripts/match_cases.py            # 普通补配（只处理 cases 为空条目）
.venv/bin/python scripts/match_cases.py --append-guiding   # 对已有 cases 条目追加指导性案例（领域门槛+上限 3）
```

案例库检索与阅读（前端 `/cases`，只读，不改表）：`GET /api/case/search?q=&source=&limit=`
（多词 AND，命中标题/案号/关键词/类别/正文）、`GET /api/case/detail?source=&loc=`
（原文按裁判要旨/基本案情/裁判理由等分节）、`GET /api/case/stats`。
注意：路径必须是单数 `/api/case/*`，复数 `/api/cases/{qid}` 是主观题接口。

### 3.5b 题库生成（客观题 / 数字判断题，2026-09-20 新增）

题库题与「当日缓存题」同表 `quizzes`，用 `origin` 区分：`daily` 当日懒生成、
`bank` 客观题库、`judge` 数字判断题库；`status=draft` 不进抽题池，抽检后 `--publish`。
自测/组卷/数判优先取题库，题库缺题才回退 LLM 现生成。

```bash
# 客观题题库：每条目 1 题
.venv/bin/python scripts/build_quiz_bank.py --only-missing --workers 6
.venv/bin/python scripts/build_quiz_bank.py --subject 民法 --limit 20
.venv/bin/python scripts/build_quiz_bank.py --publish              # 抽检后发布

# 数字判断题（数量/金额/年限/人数/期限）：法条侧 + 条目侧
.venv/bin/python scripts/build_judge_bank.py --source statutes --per-law 3
.venv/bin/python scripts/build_judge_bank.py --source entries
.venv/bin/python scripts/build_judge_bank.py --source counterparts --limit 500  # 补「错」题配平答案分布
.venv/bin/python scripts/build_judge_bank.py --publish
.venv/bin/python scripts/build_judge_bank.py --fix-subjects   # 科目口径修正
.venv/bin/python scripts/build_judge_bank.py --fix-basis      # basis 规范成「法条库主名+条号」

# 法条驱动的客观题（让「法条库补全」直接变成题库资产）
.venv/bin/python scripts/build_statute_quiz.py --dry-run
.venv/bin/python scripts/build_statute_quiz.py --only-cited --limit 50   # 先补条目引用过的条文
.venv/bin/python scripts/build_statute_quiz.py --per-law 3 --workers 6   # 每法配额补足（可多跑几轮）
.venv/bin/python scripts/build_statute_quiz.py --laws 生态环境法典 --per-law 12  # 大法加深
.venv/bin/python scripts/build_statute_quiz.py --publish

# 覆盖率与核验（每部法多少条文被题目覆盖；判断题回源核验 strict/loose）
.venv/bin/python scripts/audit_quiz_coverage.py --top 30 \
  --report ../docs/superpowers/research/2026-09-20-法条覆盖与题库核验报告.md

# 关系型判断题（情态词/程序层级/易混概念对，2026-09-20 新增）
.venv/bin/python scripts/build_relation_judge.py --source statutes --dry-run
.venv/bin/python scripts/build_relation_judge.py --source statutes --max-per-article 2 --workers 8
.venv/bin/python scripts/build_relation_judge.py --source entries --workers 8
.venv/bin/python scripts/build_relation_judge.py --source counterparts   # 同源补「错」题配平
.venv/bin/python scripts/build_relation_judge.py --publish              # 抽检后发布

# 判断题去重 / 降相似（归档可逆：status='archived'，不进抽题池，--publish 不复活）
.venv/bin/python scripts/dedupe_judge_bank.py                           # dry-run
.venv/bin/python scripts/dedupe_judge_bank.py --apply \
  --report ../docs/superpowers/research/2026-09-20-判断题去重报告.md

# 关系题覆盖审计（哪部法、哪个词族、哪些条目还没出题）
.venv/bin/python scripts/audit_relation_coverage.py --top 30 \
  --report ../docs/superpowers/research/2026-09-21-关系型判断题覆盖报告.md

# 题库概览
curl -s localhost:8090/api/quiz/bank/stats
```

**覆盖口径**：法条覆盖率 = 被题目覆盖的条文数 / 条文总数（`quizzes.basis` 能解析到该法该条）。
条目派生题只覆盖「已写进条目的考点」，所以必须用 `build_statute_quiz.py` 按法条库缺口补题；
组卷（`custom_quiz`）会留 1/3 题量给法条驱动题，否则补出来的题练不到。
判断题分两类，用 `quizzes.variant` 区分：`number` 数字型 / 17 个关系词族（`modal`、`form`、
`instance`、`review`…）关系型；`status` 新增 `archived`＝下架（保留行与答题历史）。

### 3.5c 法条题卡（条目化，2026-09-20 新增）

法条驱动**客观题**会被重建为「卡片条目」：`entries.kind='card'`、ID 形如 `XF-Q000162`，
题干/选项/答案/解析/条文摘要/朗读文本全部落在条目字段里，于是看背/听学/标记/自评/音频
复用同一条代码路径（**不新增表**）。判断题不进看背/听学（只在自测、数字判断专项、法条页）。

```bash
# 题库每次 --publish 之后重建卡片（幂等，约 1.5s / 1.2 万张）
.venv/bin/python scripts/sync_card_entries.py
.venv/bin/python scripts/sync_card_entries.py --dry-run   # 只看将新建/更新/清理多少

# 四入口覆盖审计（缺口必须为 0 且卡片与客观题 1:1）
.venv/bin/python scripts/audit_quiz_entrypoints.py \
  --report ../docs/superpowers/research/2026-09-20-法条题入口覆盖报告.md
```

**条目空间隔离（重要）**：`v_entries` 视图 = `entries WHERE kind='entry'`。
一切按「条目语义」的读取（调度、搜索、覆盖树、覆盖率、批量 TTS、出题脚本）必须走
`v_entries`；需要看见卡片的读取（看背/听学队列、标记、`/api/audio/{id}`、审阅历史、错题本）
直接读 `entries`。新增查询时先想清楚属于哪一侧，判定口径见
`docs/superpowers/specs/2026-09-20-法条题卡条目化统一-design.md` §3。

卡片 priority 统一「普通」、不强制混排：看背按调度器排序、听学按「未听优先 → 优先级」，
高优先级条目学完自然轮到卡片（自定义范围可用「内容：法条题卡」+「按法条题卡选择」直接刷）。
卡片文本由题库派生，**不支持在「看背」里就地编辑**（改了会被下次同步覆盖）。

**数字判断题的硬闸门**（`app/number_terms.py`）：「对」题的数字必须全部能在依据原文
（法条 / 条目结论）中找到；「错」题只允许改写一处数字。不满足即丢弃，避免编造数字。
中文数字与阿拉伯数字折算后比较（「三十日」==「30日」），「以内」与「内」等价，
条目号与年份不作为考点数字；纯「自某年某月某日起施行」的生效日期句不算数字考点，直接丢弃。
条目侧的题干来自「场景＋结论」，因此校验原文用两者拼接（场景里的判几年、几个月也属合法依据）。

**关系型判断题的硬闸门**（`app/relation_terms.py`，17 个词族）：「对」题不得出现原文没有的
关系词（拦住「可以↔应当」「决定↔决议」偷换）；「错」题有且仅有 1 处偷换且必须落在
`SWAPS` 白名单内（如 一审→二审、复议→复核、独任→合议庭、罚金→罚款）；机关主体必须在原文命中；
「对」题与原文单句相似度 ≥0.95 视为照抄丢弃。题干含数字时还要再过一遍数字闸门。

挂接后必须重导 entries JSON（见 3.3）才会同步 DB。指导性案例匹配机制：条目考点词 × 案例关键词/标题粗筛 → 正文核验（专用词必须命中）→ 领域门槛（刑事→刑法/刑诉，民事/知产→民法/民诉/商经知劳环+三国法涉外，行政/国赔→行政法）。

### 3.6 覆盖检查

```bash
.venv/bin/python scripts/generate_entries.py --subject 三国法 --gaps --dry-run
```

或代码内 `gap_blocks(subject, entries)`。注意：loc 跨标题边界时会把"已覆盖"误报为缺口（如三国法 CISG/信用证），复测需结合条目实际内容判断。

### 3.7 测试

```bash
.venv/bin/python -m pytest tests   # 当前 170 passed
```

## 4. 后续拓展条目的思路（方法论）

完整流水线：科目资料 → 按 `## / ###` 标题切知识块 → DeepSeek 提炼 12 字段 → 校验（来源摘录命中原文/法条可解析/长度）→ 导入 final → 音频 → 案例挂接 → 覆盖对照。拓展按性价比排序：

1. **补知识空间（上游）**：给 `data/科目资料/<科>/*.md` 加内容。新增科目需同时：建 `data/科目资料/<科>/`、`generate_entries.py` 的 `SUBJECT_PREFIX` 加前缀（如 行政法→XZ）、`scheduler.py` 与 `generator.py` 的 `SUBJECT_ORDER` 加入该科。原缺失的**环境资源法**（约 3-5 分）与**劳动法**扩容已并入 `商经知劳环`（见 `data/科目资料/商经知劳环/环境保护法-高频考点.md`、`劳动法-高频考点.md`）。
2. **真题反推（最贴"必考"，尚未做）**：拿历年真题考点与现有 point 做差集，按频次排序补——对 180 分目标性价比最高，需要真题数据源。
3. **定向补缺（中游，已实现）**：`--gaps` 只喂未被引用块；表格块用 `--batch 2`。
4. **质量校准（下游）**：priority 现为 LLM 标注，建议后续用真题频次校正；案例挂接可加 LLM 语义复核；锚点/结论人工抽检。
5. **180 分权重参考（客观题 300 分，过线 180）**：商经 58-60 / 理论法 50 / 民法 45-48 / 刑法 37-39 / 刑诉 30-33 / 民诉 30 / 行政法 25-26 / 三国法 18-20。优先级 = 权重 × 频次 × 性价比；普通类条目（当前约 8%）不必追全。

## 5. 已踩坑记录（2026-08-29 实战）

- 条目字数字硬限制曾把 conclusion 切在法条号中间（如「民诉法第2。」），全库 31 条结论、
  3 条 TTS、110 条 anchor 受损；2026-09-15 已移除硬限制、只保留提示词建议区间与 WARN，
  修复脚本见 `backend/scripts/fix_truncated_entries.py`。
- 重导 entries JSON 会把全部行打回 `draft`，全库查询立即失效 → 必须再 promote。
- `import_guiding_cases.py` 曾按 loc 单键重写 index.csv 丢 1000+ 行 → 已改 `(来源库, 定位符)` 键并加回归测试。
- 精选汇编 30 个指导性案例 id 全部已在统一库中，合并价值在正文/关键词增强，不新增行。
- 行政法生成偶发 anchor 短于 16 字被丢弃（LLM 输出波动），重跑对应 `--gaps` 即可。
- 追加指导性案例后 240 条条目超 3 条上限被裁剪（优先保留指导性案例），原始引用可在 git 历史恢复。
- README 中 TTS 描述需以 `backend/app/config.py` 为准（qwen-tts 链 + Ethan，非 qwen3-tts-instruct-flash/Neil）。

## 6. 2026-09-20 实战补充

- **截断录音**：历史上有 4 条 wav 只录了开头（SJ-677 87 字只录 5.8 秒，重合成 19.0 秒；
  SG-339/SG-355/SJ-618 同类）。`audit_tts.py` 用语速阈值现可自动抓出，已全部重合成并建台账。
- **文本改了必须重合成**：`tts_assets.text_hash` 与当前归一文本不一致即判陈旧。
  2026-09-15/09-20 两次改条目文本后有 13 条音频是旧的，已重合成。
- **备用 key**：`DASHSCOPE_API_KEY_FALLBACK`（.env）只在主 key 的全部 TTS 模型失败时启用；
  2026-09-20 实测主 key 三模型均可用，备用通道仅作降级保险。
- **题库表结构**：`quizzes` 增加 `entry_id`(可空) / `subject` / `point` / `origin` / `basis` /
  `status` / `text_hash`，`qtype` 扩展 `judge`；旧库由 `db.connect()` 幂等重建升级
  （会先把旧表备份到 `data/backup/`，该目录已 gitignore）。
- 反查「数字」而非考点的干扰：法条里的公布日期、条号不属于考点数字，已在
  `number_terms.extract` 中排除。
