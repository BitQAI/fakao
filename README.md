# 法考冲刺工具

17 天冲刺用的个人 AI 法考教练（移动端 Web）。每天动态倒排学习队列，看背/听学/自测三种方式，AI 早报晚报复盘与实时答疑，覆盖树监控进度。

设计：`docs/superpowers/specs/2026-08-27-法考冲刺工具-design.md`
实施计划：`docs/superpowers/plans/2026-08-27-法考冲刺工具.md`
AI 操作指南：`AGENTS.md`（供 AI 代理读取：条目生成/补缺/导入/音频/案例挂接/覆盖检查，以及后续拓展条目的方法论）

## 部署（Ubuntu 22）

1. 安装依赖：

```bash
sudo apt update
sudo apt install -y python3-venv nginx git
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

2. 克隆仓库并建密钥文件：

```bash
sudo mkdir -p /opt/fakao && sudo chown $USER /opt/fakao
git clone <你的仓库地址> /opt/fakao
cd /opt/fakao
cp .env.example .env
vi .env   # 填入 DEEPSEEK_API_KEY
          # 听学 TTS 另填 DASHSCOPE_API_KEY（千问 qwen-tts 链，音色 Ethan；TTS_MODELS/TTS_VOICE/TTS_SPEED 可配）
```

3. 后端安装与导入数据：

```bash
cd /opt/fakao/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/import_entries.py data/entries/*.json
.venv/bin/python scripts/load_cases.py   # 案例原文查询；见下方「案例数据说明」
```

> **案例数据说明**：`data/案例数据/`（约 69MB）与 `data/案例库统一/documents/`
> 均被 .gitignore 排除。若要使用看背/听学的「案例原文」功能，需在服务器上
> 上传这两份目录（或仅上传 documents/），再运行
> `.venv/bin/python scripts/load_cases.py`。不装也不影响其余功能，仅案例原文
> 显示「原文不可用」。

4. 前端构建（standalone 模式需手动拷贝静态资源）：

```bash
cd /opt/fakao/frontend
npm ci
npm run build
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public
```

5. 配置 systemd 与 Nginx：

```bash
sudo cp deploy/fakao-backend.service deploy/fakao-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fakao-backend fakao-frontend
sudo cp deploy/nginx.conf /etc/nginx/sites-available/fakao
sudo ln -s /etc/nginx/sites-available/fakao /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow 80/tcp
```

6. 打开 `http://<服务器IP>`，手机浏览器访问即用。有域名可再加 HTTPS（certbot）。

## 使用

- 今日：看倒计时、早报、今日计划与入口
- 学习：看背（翻卡自评）/ 听学（白天挂着听）/ 自测（每日 10 题）
  - 自测子页签：今日 / 组卷 / **数判** / 历史。**数判**是「数」专项——
    只考数量、金额、年限、人数、期限、比例，逐题判对错，错了立刻给正确值与法条依据
  - 学习 → 案例：主观题模块（按真实卷面 5 道大题组织）
  - 今日案例：微主观题（第 2/3/5 题练习），写要点或只听，听完必须勾采分点
  - 论述题：第 1 题习近平法治思想，材料驱动，600 字以上；提交后给字数与「照搬材料」检查
  - 综合大案例：第 4 题民法＋民诉＋商法，8—13 小问，采分点按小问分组勾选
  - 复盘池：按采分点聚合的未命中点，反复踩同一个点才算真薄弱
- 报告：晚报复盘与覆盖树
- 我的：考试日期、每日上限、数据导入、DeepSeek 状态
- AI 助手：右下悬浮钮随时提问，看背卡片内可针对当前考点提问

## 开发

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm run dev   # /api 自动代理到 8000
```

### 主观题题库生成（在 `backend/` 下执行）

```bash
.venv/bin/python scripts/build_case_questions.py --subject 刑法 --limit 5   # 案例分析
.venv/bin/python scripts/build_essay_questions.py --list                    # 论述题候选专题
.venv/bin/python scripts/build_essay_questions.py --topic 依宪治国          # 生成论述题
.venv/bin/python scripts/build_composite_questions.py --limit 2             # 综合大案例
```

### 客观题题库 / 数字判断题题库生成（在 `backend/` 下执行）

```bash
.venv/bin/python scripts/build_quiz_bank.py --only-missing --workers 6   # 条目 → 客观题库
.venv/bin/python scripts/build_quiz_bank.py --publish                    # 抽检后发布
.venv/bin/python scripts/build_statute_quiz.py --per-law 3 --workers 6   # 法条库 → 客观题库
.venv/bin/python scripts/build_statute_quiz.py --publish
.venv/bin/python scripts/build_judge_bank.py --source statutes --per-law 3
.venv/bin/python scripts/build_judge_bank.py --source entries
.venv/bin/python scripts/build_judge_bank.py --source counterparts --limit 500
.venv/bin/python scripts/build_judge_bank.py --publish
.venv/bin/python scripts/audit_quiz_coverage.py --top 30 \
  --report ../docs/superpowers/research/2026-09-20-法条覆盖与题库核验报告.md
```

题库题与当日缓存题同表（`quizzes`，按 `origin` 区分）；自测/组卷/数判优先取题库，
题库缺题才回退 LLM 现生成。组卷会留约 1/3 题量给「法条驱动题」（basis 有值、不挂条目），
保证法条库补全的内容能被练到。数字判断题有硬校验：题干数字必须能在法条/结论原文中找到。

### TTS 质检与修复（在 `backend/` 下执行）

```bash
.venv/bin/python scripts/audit_tts.py --report ../docs/superpowers/research/2026-09-20-TTS质检报告.md
.venv/bin/python scripts/repair_tts.py                    # dry-run
.venv/bin/python scripts/repair_tts.py --apply            # 重合成异常/陈旧录音
.venv/bin/python scripts/repair_tts.py --apply --backfill # 给健康音频补台账
```

产物入库为 `draft`，人工抽检后加 `--publish`（只发布该题型）转为 `published`。

**判分口径**：采分点出自裁判理由或备考资料原文，用户逐条勾「我写到了吗」计分，
**不让 LLM 评判主观文字**；论述题另加两项确定性检查——字数是否达标、是否大段照搬材料。

## 验收清单

见 `docs/superpowers/plans/2026-08-27-法考冲刺工具.md` Task 20：导入 → 今日 → 看背 → 听学（含案例原文）→ 自测 → 复盘/覆盖 → AI 助手 → 降级验证。
