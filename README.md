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
- 报告：晚报复盘与覆盖树
- 我的：考试日期、每日上限、数据导入、DeepSeek 状态
- AI 助手：右下悬浮钮随时提问，看背卡片内可针对当前考点提问

## 开发

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm run dev   # /api 自动代理到 8000
```

## 验收清单

见 `docs/superpowers/plans/2026-08-27-法考冲刺工具.md` Task 20：导入 → 今日 → 看背 → 听学（含案例原文）→ 自测 → 复盘/覆盖 → AI 助手 → 降级验证。
