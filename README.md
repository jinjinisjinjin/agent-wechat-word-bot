# 微信单词机器人（wechat-word-bot）

通过微信接收单词（中/英文均可），自动查词、记录，并按遗忘曲线定时推送复习提醒与周报的英语学习机器人。

- 英文单词 → 音标 + 英文释义 + **中文释义** + 例句，自动入库
- 中文词汇 → 自动中译英后查词典，返回英文释义卡
- 每个单词设定 5 个复习节点（第 1/2/4/7/15 天），到期主动推送
- 每日复习推送附带一道词义配对选择题（A/B/C/D），答对自动推进复习
- `/stats` 查看总词数、待复习数、高频词 Top3
- 每周一早上自动推送学习周报

---

## 架构

```
微信  ←→  iLink Bot API  ←→  cc-weixin-bridge（Node，桥接）
                              │  POST 消息到
                              ▼
                    Flask /webhook (Python, 端口 9090)
                              │
              ┌───────────────┼─────────────────┐
              ▼               ▼                 ▼
      message_handler    word_service      history_manager
      （分发/格式化）    （查词+翻译）       （JSON 数据）
              │               │
              ├─ quiz_manager（测验）  scheduler（定时任务）
              └─ weekly_report（周报）
```

> **为什么要 fork 改造 cc-weixin？**
> 原版 `cc-weixin`（npm 包）基于腾讯官方 **iLink Bot API**，合法安全；但它只把消息喂给 Claude，不支持转发到自定义 webhook。本项目把其中的「调 Claude」改为「POST 到本地 Flask `/webhook` 取回 reply」，复用其扫码登录与消息收发，去掉了 Claude 依赖。

---

## 环境要求

| 组件 | 版本要求 | 本项目实测 |
|------|---------|-----------|
| Node.js | ≥ 22 | v22 / v24 均可 |
| Python | ≥ 3.8 | 3.8.0 最低线，代码保持 3.8 兼容 |
| npm / pip | 可用 | — |

---

## 安装与启动

### 1. 安装桥接依赖（首次，需在项目目录执行）

```bash
cd ~/wechat-word-bot/cc-weixin-bridge
npm install
```

### 2. 一键启动

```bash
cd ~/wechat-word-bot
chmod +x start.sh
./start.sh
```

脚本会依次：安装 Python 依赖 → 后台启动 Flask(9090) → 启动桥接并打印**登录二维码**。

### 3. 微信扫码登录

用手机微信扫描终端出现的二维码，并点击「确认登录」。看到：

```
✅ 已连接（Bot: xxxxx@im.bot）
🚀 开始长轮询收消息（Ctrl+C 退出）...
```

即连接成功。session 持久化在 `~/.cc-weixin/token.json`，**下次启动免扫码**。

### 4. 在微信里使用

给该 Bot 发消息即可：

| 发送内容 | 效果 |
|---------|------|
| `hello`（英文单词）| 返回音标/释义/中文/例句，并入库 |
| `苹果`（中文词汇）| 中译英后查词典，返回英文释义卡 |
| `/stats` 或 `统计` | 学习统计（总词数/待复习/高频词 Top3）|
| `A` / `B` / `C` / `D` | 回答当日复习推送中的选择题 |

---

## 配置说明

### 端口

默认使用 **9090**（避开 macOS 系统占用的 5000/8080）。涉及 6 处，需保持一致：

- 根目录 `.env`：`PORT=9090`
- `main.py`：默认端口 + `app.run(..., threaded=True)`
- `cc-weixin-bridge/.env`：`WEBHOOK_URL=http://localhost:9090/webhook`
- `cc-weixin-bridge/lib/webhook.mjs`：fallback 地址
- `start.sh`：提示文案

如需改端口，请同步修改以上 6 处。

### 翻译源

中文释义 / 中文查词使用免 Key 的多源翻译（按优先级）：

1. **MyMemory**（`api.mymemory.translated.net`，免费，国内通常可达）
2. **Google 翻译** 作为兜底（部分网络环境可达）

任一成功即返回，全部失败则优雅降级（不阻塞主流程、不报错给用户）。

---

## 定时任务

由 `scheduler.py`（后台线程运行）驱动：

- **每天 08:00** `daily_job()`：推送当天待复习单词 + 一道测验题。
- **每周一 08:30** `weekly_job()`：推送上周学习周报（新增词数、完成复习数、热词 Top3）。

> 定时任务依赖本机保持运行；若要长期稳定推送，建议部署到云服务器（见下）。

---

## 数据存储

所有学习记录保存在 `~/word_history.json`，每条记录字段：

```json
{
  "word": "apple",
  "phonetic": "/ˈæpl/",
  "meaning": "[n] a round fruit",
  "meaning_zh": "苹果",
  "examples": ["I ate an apple."],
  "synonyms": ["fruit"],
  "query_count": 1,
  "added_date": "2026-07-08",
  "review_dates": ["2026-07-09", "2026-07-10", "2026-07-12", "2026-07-15", "2026-07-23"],
  "next_review_index": 0,
  "meanings_detail": [
    {"partOfSpeech": "n", "definition": "a round fruit", "example": "I ate an apple.", "zh": "苹果"}
  ]
}
```

- 重复查同一词：仅累加 `query_count`，**不重置**复习计划。
- 待复习数 = `next_review_index < 5` 的词数量。

---

## 常见问题

**Q：启动报 `Address already in use` / 端口被占？**
A：旧的 Flask/桥接没退出。先清理再启动：
```bash
lsof -ti :9090 | xargs kill -9
cd ~/wechat-word-bot && ./start.sh
```

**Q：回复很慢？**
A：已做三重优化——`requests.Session()` 复用连接、内存缓存、历史命中免联网。若首次查词仍慢，多为网络因素（词典/翻译接口延迟）。

**Q：中文释义偶尔为空？**
A：翻译接口网络波动会导致降级，仅显英文。重试或稍后再查即可。

**Q：想换端口 / 翻译源？**
A：端口改 6 处配置；翻译源在 `word_service.py` 的 `_TRANSLATE_SOURCES` 中调整。

---

## 下一步：部署到云端（可选）

当前运行在你个人电脑上，关机会中断推送。若希望 7×24 稳定服务，可：

1. 将整个 `~/wechat-word-bot` 目录上传到一台云服务器（或 Container）。
2. 用 `nohup ./start.sh &` 或 `systemd` / `supervisor` 托管进程。
3. 注意：iLink 登录 session 需在该服务器上重新扫码一次。

---

## 目录结构

```
~/wechat-word-bot/
├── main.py              # 主入口：Flask /webhook + 定时任务线程
├── word_service.py      # 查词服务 + 中英/英中翻译
├── history_manager.py   # JSON 数据管理（8 个查询/更新函数）
├── message_handler.py   # 消息分发：查词 / 中文查词 / 统计 / 测验
├── quiz_manager.py      # 测验生成与答题判断
├── scheduler.py         # 每日复习 + 每周周报定时任务
├── weekly_report.py     # 周报生成
├── requirements.txt     # Python 依赖
├── start.sh             # 一键启动脚本
├── .env                 # 端口等配置
├── README.md            # 本文档
└── cc-weixin-bridge/    # fork 改造后的微信桥接（Node）
    ├── cc-weixin.mjs    # 入口：扫码登录 + 长轮询 + 转发到 webhook
    ├── lib/webhook.mjs  # 把消息 POST 到 Flask 并取回 reply
    ├── package.json
    └── .env             # WEBHOOK_URL 配置
```
