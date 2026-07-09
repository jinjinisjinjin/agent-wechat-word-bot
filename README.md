# 微信单词机器人（wechat-word-bot）

通过微信接收单词（中/英文均可），自动查词、记录，并按遗忘曲线定时推送复习提醒与周报的英语学习机器人。

- 英文单词 → 音标 + 英文释义 + **中文释义** + 例句，自动入库
- 中文词汇 → 自动中译英后查词典，返回英文释义卡
- 每个单词设定 5 个复习节点（第 1/2/4/7/15 天），到期主动推送
- 每日复习推送附带一道词义配对选择题（A/B/C/D），答对自动推进复习
- `/stats` 查看总词数、待复习数、高频词 Top3
- 每周一早上自动推送学习周报

---

## 三种运行方式

项目支持三条互相独立的通道，按需选用：

| 通道 | 入口 | 运行位置 | 是否需要本机在线 | 说明 |
|------|------|----------|----------------|------|
| **微信版** | 微信里直接私聊 Bot | 本机 + cc-weixin-bridge 扫码 | ✅ 需要 | 个人微信机器人，依赖非官方桥接，适合自己用 |
| **公众号版（本机）** | 微信公众号对话框 | 本机跑 `python main.py` + 隧道 | ✅ 需要 | 走微信官方 API，合法合规 |
| **公众号云版** ✅推荐 | 微信公众号对话框 | 腾讯云 SCF 7×24 | ❌ 不需要 | 部署到云端，关注即收欢迎语、随时查词，不受本机开关影响 |

> 一般用户**直接用公众号云版**最省心：关注公众号即可，零风险、零维护。微信版上云有个人号封号风险，不推荐。

---

## 架构

### 微信版（本机）

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

### 公众号版（官方 API）

```
用户微信  →  微信公众号  →  微信服务器  →  你的服务（/wechat 回调）
                                            │
                              Flask (wechat_official.py)
                                            │
              ┌───────────────┼─────────────────┐
              ▼               ▼                 ▼
      message_handler    word_service      history_manager
```

- **本机版**：回调地址指向本地 `main.py`（需内网穿透隧道，如 ngrok/natapp）。
- **云版**：回调地址指向腾讯云 SCF 函数 URL（`https://<id>.ap-shanghai.tencentscf.com/wechat`），7×24 在线。

---

## 环境要求

| 组件 | 版本要求 | 本项目实测 |
|------|---------|-----------|
| Node.js | ≥ 22 | v22 / v24 均可 |
| Python | ≥3.8 | 3.8.0 最低线，代码保持 3.8 兼容 |
| npm / pip | 可用 | — |
| 公众号云版额外需 | 腾讯云账号 | 免费额度即可 |

---

## 一、微信版（本机）

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

## 二、公众号版（本机 + 隧道）

1. 配置 `.env`：`WECHAT_CHANNEL=official`、`MP_APPID`、`MP_APPSECRET`、`MP_TOKEN`。
2. 运行 `python main.py`，Flask 监听 `MP_CALLBACK_PATH`（默认 `/wechat`）。
3. 用隧道（ngrok/natapp）把本地端口暴露为公网 URL。
4. 公众号后台「开发接口管理 → 服务器配置」填该 URL + Token，提交。
5. 关注公众号即可收到欢迎语、发单词查词。

> 本机版依赖终端在线 + 隧道稳定。若要 7×24 稳定服务，见下一节「公众号云版」。

---

## 三、公众号云版（腾讯云 SCF 7×24）✅ 推荐

把服务部署到腾讯云 SCF Web 函数，实现**关注即欢迎、随时查词、不受本机开关影响**。

**关键步骤（踩坑全集见 [README-踩坑记录.md](README-踩坑记录.md)）：**

1. 腾讯云新建函数：**从头开始 → Web 函数 → 本地上传 ZIP**（⚠️ 别选 Flask 模板，会掉进 Cloud Studio 找不到上传入口）。
2. 代码改造：`scf_bootstrap` 设 `PORT=9000`、`DATA_DIR=/tmp`、`PYTHONPATH=/var/user/lib`；数据路径改读 `DATA_DIR`；Flask 绑定 `0.0.0.0:PORT`。
3. 依赖预装进 `lib/`（SCF 自带 pip 是坏的，云端装不了）：本机下载 cp39-manylinux wheel 解压进 `lib/`；**urllib3 必须 <2**（OpenSSL 1.0.2k 不兼容 v2）。
4. 打包上传（排除 `.env`、日志、用户数据）。
5. 函数「环境变量」注入 `WECHAT_CHANNEL` / `MP_TOKEN` / `MP_APPID` / `MP_APPSECRET` / `MP_CALLBACK_PATH`。
6. 开启「函数 URL」公网访问（API 网关已停售新用户）。
7. 公众号后台「服务器配置」URL 填函数 URL + `/wechat`，Token 与云端环境变量一致，提交。

完整部署流程见仓库内 **[CLOUD_DEPLOY.md](CLOUD_DEPLOY.md)**；避坑细节见 **[README-踩坑记录.md](README-踩坑记录.md)**。

> **密钥轮换提醒**：改 `MP_TOKEN` / `MP_APPSECRET` 时，**先改云端环境变量并部署，再改公众号后台 Token 提交**，顺序反了微信验证失败。云端走环境变量注入，轮换无需重传 zip。

---

## 配置说明

### 端口（微信版）

默认使用 **9090**（避开 macOS 系统占用的 5000/8080）。涉及 6 处，需保持一致：

- 根目录 `.env`：`PORT=9090`
- `main.py`：默认端口 + `app.run(..., threaded=True)`
- `cc-weixin-bridge/.env`：`WEBHOOK_URL=http://localhost:9090/webhook`
- `cc-weixin-bridge/lib/webhook.mjs`：fallback 地址
- `start.sh`：提示文案

如需改端口，请同步修改以上 6 处。

### 公众号环境变量

| 变量 | 说明 |
|------|------|
| `WECHAT_CHANNEL` | `personal`（微信版）/ `official`（公众号版） |
| `MP_APPID` | 公众号 AppID |
| `MP_APPSECRET` | 公众号 AppSecret（重置后需同步更新） |
| `MP_TOKEN` | 与公众号后台「服务器配置」Token 一致的共享口令 |
| `MP_CALLBACK_PATH` | 回调路径，默认 `/wechat` |

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

> 定时任务依赖本机/云端保持运行；公众号云版部署后由 SCF 常驻保障。

---

## 数据存储

所有学习记录保存在 `~/word_history.json`（云端为 `DATA_DIR` 下），每条记录字段：

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

**Q：公众号关注后没收到欢迎语？**
A：启用「服务器配置」后，公众号后台的被关注自动回复会**失效**，欢迎语改由你的服务在收到关注事件时下发。若服务离线（本机终端关了 / 云函数没部署），则无欢迎语。→ 用公众号云版（SCF 7×24）即可根治。

**Q：云端函数 URL 提交公众号配置报超时？**
A：多半是依赖没装好（SCF 自带 pip 坏）或 urllib3 版本不兼容 OpenSSL。详见 [README-踩坑记录.md](README-踩坑记录.md)。

---

## 目录结构

```
~/wechat-word-bot/
├── main.py              # 主入口：Flask 回调 + 定时任务线程
├── word_service.py      # 查词服务 + 中英/英中翻译
├── history_manager.py   # JSON 数据管理（8 个查询/更新函数）
├── message_handler.py   # 消息分发：查词 / 中文查词 / 统计 / 测验
├── quiz_manager.py      # 测验生成与答题判断
├── scheduler.py         # 每日复习 + 每周周报定时任务
├── weekly_report.py     # 周报生成
├── wechat_official.py   # 公众号回调处理（欢迎语 / 查词）
├── requirements.txt     # Python 依赖
├── start.sh             # 微信版一键启动脚本
├── scf_bootstrap        # 腾讯云 SCF 启动脚本
├── .env                 # 端口 / 公众号等配置（勿提交密钥）
├── cc-weixin-bridge/    # fork 改造后的微信桥接（Node，微信版用）
├── CLOUD_DEPLOY.md     # 公众号云版（SCF）部署指南
├── README-公众号版.md   # 公众号版独立说明
├── README-踩坑记录.md   # 全项目踩坑实录
└── WECHAT_OFFICIAL_SETUP.md  # 公众号配置步骤
```

---

## 相关文档

- [CLOUD_DEPLOY.md](CLOUD_DEPLOY.md) — 公众号云版（腾讯云 SCF）完整部署指南
- [README-公众号版.md](README-公众号版.md) — 公众号版独立使用说明
- [README-踩坑记录.md](README-踩坑记录.md) — 从打包、上云到密钥轮换的全部踩坑记录
- [WECHAT_OFFICIAL_SETUP.md](WECHAT_OFFICIAL_SETUP.md) — 公众号后台配置步骤
- [GitHub上传方法.md](GitHub上传方法.md) — 免密码（钥匙串取 token）上传文件到 GitHub 的方法
