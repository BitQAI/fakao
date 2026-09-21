# 法条题卡 TTS 台账、预热与全量生成 — Spec（2026-09-20）

## 1. 用户决策（已拍板）

1. **选方案 A**：卡片音频仍以按需合成为主，但把「马上会听到的那批」预热掉，并把质检口径
   覆盖到卡片；不做默认全量预合成。
2. **卡片单独建 `tts_assets` 台账**，字段与条目完全同构（`text_hash` / `speed` / `bytes` /
   `duration_sec` / `created_at`），条目与卡片共用一张表、按 `entry_id` 前缀区分
   （卡片 ID = `<科目前缀>-Q<题号六位>`）。不新增表。
3. **全量生成（12051 张）可用多 agent 分片并行**，脚本需支持分片参数；
   实际开跑前先给出实测吞吐与耗时估算。

## 2. 现状与缺口（2026-09-20 实测）

| 项目 | 数值 |
|---|---|
| 已发布法条驱动客观题（`origin='bank'`） | 12052 |
| 卡片条目 `entries.kind='card'`（final） | 12052，`tts_text` 100% 非空 |
| 卡片已有音频 | 1（`XF-Q003841`） |
| 卡片缺音频 | 12051 |
| 卡片 `tts_assets` 记录 | 0 |
| 卡片朗读文本总量 | 541.9 万字（平均 450 字/张，最长 1055 字） |
| 听学池未听 | 12053 条，其中**前 200 条有 199 条是卡片** |

根因不是 bug，是口径：`scripts/synthesize_audio.py`、`scripts/audit_tts.py`、
`scripts/repair_tts.py` 的扫描源都是 `v_entries`（`WHERE kind='entry'`），卡片被刻意排除在
「条目空间」之外（见 `tests/test_entry_isolation.py`）；卡片走 `/api/audio/{id}` →
`tts.ensure_mp3()` 的按需合成，且**不写台账**。

后果两条：① 听学池头部几乎全是卡片，首播要等一次完整合成；② 卡片音频永远进不了
`audit_tts.py` 的视野，截断/无声这类问题无人发现。

### 2.1 合成吞吐实测（本次探测，主 key 正常）

| 并发 | 样本 | 墙钟 | 吞吐 |
|---:|---:|---:|---:|
| 1 | 1 张（273 字） | 22.1s | — |
| 8 | 12 张 | 61.2s | 79.6 字/秒 |
| 16 | 32 张 | 94.5s | 150.6 字/秒 |

16 并发仍在近线性区（未见限流）。按 150 字/秒折算 541.9 万字 ≈ **10 小时**；
3 分片 × 16 并发理论 ≈ 3.3 小时。**金额以 DashScope 账单口径为准，本 Spec 不臆造单价。**

## 3. 方案

### 3.1 台账（`tts_assets` 覆盖卡片）

- 所有合成路径（预热 / 全量 / 修复 / 按需）成功后统一调用既有
  `tts.record_asset()`（已具备 upsert 幂等），字段与条目同构，不做任何表结构变更。
- 按需路径补齐建档：`tts.ensure_mp3(entry_id, text, *, dry_run=False, conn=None)` 增加可选
  连接参数，**仅当本次真的新生成了音频**且 `conn` 非空时写台账；`/api/audio/{id}` 传入请求
  连接。条目与卡片共用该逻辑（等于顺带消灭条目的 `untracked`）。
- 文本漂移作废保持现状：`card_entries._drop_audio()` 已同时删 wav 与台账行。

### 3.2 质检（卡片单列一档，不污染条目口径）

- `app/tts_audit.py`：`summarize(issues, *, repair_kinds=DEFAULT_REPAIR_KINDS)`，保持默认行为
  不变（`missing/empty/stale/suspect`）。
- `scripts/audit_tts.py` 增 `--kind {entry,card,all}`，**默认 `entry`**（向后兼容，
  `v_entries` 隔离原则不变）：
  - `card` 档：`missing` 记为「待生成」（正常状态，12051 张），**不进 `repair_ids`**；
    `repair_ids` 只含 `empty/stale/suspect`（真坏录音）；`untracked` 单列。
  - 卡片档扫描 `entries WHERE kind='card' AND status='final' AND tts_text != ''`。
- `scripts/repair_tts.py` 增 `--kind {entry,card,all}`（默认 `entry`）：卡片档只修
  `empty/stale/suspect` 与显式 `--ids`；**卡片缺音频不自动批量合成**——那是
  `synthesize_cards.py` 的职责，避免误触发 1.2 万条付费调用。
- `scripts/synthesize_audio.py` 保持 entries-only 不动。

### 3.3 预热（听学队列头部）

- `service.py` 新增薄封装 `listen_card_ids(conn, limit)`：按既有听学排序
  （未听优先 → 次数少 → 久未听 → 优先级 → 科目 → id）返回队列里的卡片 ID。
  排序逻辑仍只有 `_sort_listen_items` 一处实现，脚本不复刻。
- 新脚本 `scripts/synthesize_cards.py --queue N`（默认 200）：取队列前 N 张中**缺音频**的
  卡片进行合成。N 以外的卡片维持按需合成。

### 3.4 全量生成（分片，供多 agent 并行）

- `scripts/synthesize_cards.py --all --shard I/N --workers W`：
  - 候选集 = 卡片中缺音频或 0 字节者，按 `id` 稳定排序后 **步长分片** `rows[I-1::N]`
    （步长比连续切片更均衡：题目按科目聚集，连续切片会让某片全是大题）。
  - 网络合成走线程池（沿用 `repair_tts` 的「主线程落盘 + 写台账」模式，避开 SQLite 多线程
    写）；失败重试 2 次，失败不写 0 字节文件；已存在非空 wav 直接跳过 → 可中断续跑。
  - 多 agent 分工：每个 agent 只跑一个分片并汇报进度，互不重叠、天然幂等。

## 4. 边界与约束

- 不破坏「条目空间隔离」：条目侧脚本继续读 `v_entries`，卡片走新脚本 / `--kind card`。
- 不新增表、不新增列、不引入新依赖。
- 合成失败不得产生 0 字节缓存文件，也不得覆盖已有可用音频。
- SQLite 多进程并发写：沿用 `db.connect()` 的 `timeout=30`；台账写入逐条 commit，
  单条 upsert 极短，实测风险低。
- 前端零改动（`/api/audio/{id}` 已通用）。

## 5. 验证标准

1. `pytest tests` 全绿；新增测试覆盖：卡片建台账、卡片 audit 把 `missing` 归为待生成、
   `listen_card_ids` 顺序、分片并集等于全集且互不重叠。
2. 实跑 `--queue 200`：卡片有音频数从 1 增至 ≈201，`tts_assets` 同数；
   `audit_tts.py --kind card` 显示待生成 ≈ 12051-200，坏录音 0。
3. 抽检 ≥3 张卡片：`duration_sec > 0` 且语速落在 3.0~6.5 字/秒。
4. `GET /api/audio/<已预热卡片ID>` 直接命中缓存（毫秒级返回，无合成延迟）。
5. 全量生成前给出分片实测吞吐与预计完成时间供用户确认。

## 6. 范围边界

- 不做：卡片默认全量预合成、质检告警落库、听学接口内的自动预热触发（本轮只提供脚本，
  是否挂定时任务后续单独决策）。
