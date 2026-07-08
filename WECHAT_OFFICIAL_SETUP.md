# 微信公众号接入指南（测试号 / 订阅号）

本指南说明如何把 `wechat-word-bot` 从「个人微信（cc-weixin）」切换到「微信公众号」通道，
让用户通过公众号发消息来查词 / 复习 / 测验。

---

## 一、架构说明

```
用户微信  ──(发消息)──▶  微信公众号服务器
                            │  POST XML（回调 URL）
                            ▼
                    本机 Flask 服务  /wechat 路由
                            │
                            ▼
                  wechat_official.handle_update()
                            │
              ┌─────────────┴─────────────┐
        同步快路径（<4s）            异步路径（网络慢）
        被动回复 XML              先回“查询中”→ 客服消息补推
                            │
                            ▼
                  message_handler.handle_text()（复用原有全部逻辑）
```

- 个人微信通道（`/webhook`，cc-weixin 桥接）**保留**，通过 `WECHAT_CHANNEL` 切换。
- 公众号通道新增 `/wechat` 路由，支持 GET 验证 + POST 收消息（明文模式）。

---

## 二、公众号后台配置（需你操作）

> 本指南以「接口测试号」为例（开发最方便、免认证）。订阅号步骤基本一致。

### 1. 获取测试号
打开 https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login
用微信扫码登录，页面会直接给你：
- **appID**
- **appsecret**
- `URL` 填写框、`Token` 填写框（在下方「接口配置信息」区）

### 2. 填写接口配置
在「接口配置信息」处填写：

| 字段 | 填什么 |
|------|--------|
| **URL（服务器地址）** | `https://你的公网域名或ngrok地址/wechat` |
| **Token（令牌）** | `jZU6MqOdiKd8SVsuNFABcgUAHaI3W603` |

> ⚠️ Token 必须与项目 `.env` 里的 `MP_TOKEN` **完全一致**（已为你生成并写入 `.env`）。
> URL 的**路径部分必须是 `/wechat`**，与 `MP_CALLBACK_PATH` 一致。

### 3. 消息加解密方式
开发期选择 **明文模式**（最简单，无需 EncodingAESKey）。
后续上生产可改为「安全模式」，届时用备用 `MP_AESKEY=AMcH4UjD1MLVIeGxOituZYlKrY5Ifdx0TbnCTXkFjf9`。

### 4. 填写 appID / appsecret 到 .env
编辑 `~/wechat-word-bot/.env`：
```
MP_APPID=你页面上的appID
MP_APPSECRET=你页面上的appsecret
```

---

## 三、代码修改清单

| 文件 | 改动 |
|------|------|
| `wechat_official.py`（新增） | 公众号接入全部逻辑：签名校验、XML 解析/封装、access_token 缓存、客服消息异步推送、订阅者记录、消息去重 |
| `main.py` | 新增 `/wechat` 路由（GET 验证 + POST 收消息）；`send_weixin` 按 `WECHAT_CHANNEL` 切换通道（official 走客服消息推送） |
| `.env` / `.env.example` | 新增 `WECHAT_CHANNEL`、`MP_TOKEN`、`MP_APPID`、`MP_APPSECRET`、`MP_CALLBACK_PATH` |
| `.gitignore` | 忽略 `mp_token.json`、`mp_subscribers.json` 运行时状态 |

---

## 四、本地调试（ngrok 内网穿透）

微信要求回调地址为公网可达。本机开发用 ngrok 临时暴露：

```bash
# 1. 安装 ngrok（如未装）
brew install ngrok

# 2. 启动机器人（确保 .env 中 WECHAT_CHANNEL=official，且填好 MP_APPID/MP_APPSECRET）
cd ~/wechat-word-bot
./start.sh            # 或：python3 main.py &

# 3. 另开终端，用 ngrok 把本地 9090 暴露到公网 https
ngrok http 9090
```

ngrok 会给出形如 `https://xxxx.ngrok-free.app` 的地址。把它的 `/wechat` 拼上：
```
URL = https://xxxx.ngrok-free.app/wechat
```
填到测试号后台「接口配置信息」→ 点「提交」，微信会立即发 GET 验证，看到「配置成功」即握手完成。

> 💡 ngrok 免费版每次重启地址会变，改完 URL 需回后台重新提交一次。
> 也可改用 **natapp**（国内稳定，固定隧道需付费）。

---

## 五、云服务器正式部署（以 Nginx 为例）

1. 把代码推到服务器（git clone 你的仓库）。
2. 安装依赖：`pip install -r requirements.txt`；桥接如不需要可不装。
3. 用进程管理器（systemd / supervisor / nohup）常驻 `python3 main.py`（监听 9090）。
4. Nginx 反代 443 → 9090，并配置 HTTPS 证书（Let's Encrypt 免费）：

```nginx
server {
    listen 443 ssl;
    server_name your.domain.com;
    ssl_certificate     /path/fullchain.pem;
    ssl_certificate_key /path/privkey.pem;

    location /wechat {
        proxy_pass http://127.0.0.1:9090/wechat;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

5. 公众号后台 URL 填 `https://your.domain.com/wechat`。
6. 若开启了 **IP 白名单**（公众号后台「基本配置」→「IP 白名单」），把**服务器出网 IP** 加进去，
   否则获取 access_token（客服消息推送所需）会被拒。

---

## 六、5 秒超时与异步推送说明

- 订阅号 / 测试号的被动回复必须在 **5 秒内**返回。
- 本实现策略：
  - **快路径**：查词在 4 秒内完成（如历史命中、网络通畅）→ 直接被动回复 XML，体验最佳。
  - **慢路径**：超过 4 秒（新词 + 网络慢）→ 先被动回复「⏳ 正在查询，请稍候...」，
    原查词任务完成后通过**客服消息接口**补推结果。
- 客服消息要求用户 **48 小时内互动过**；用户刚发消息即处于窗口内，可正常推送。

---

## 七、测试验证（端到端）

1. 启动机器人 + ngrok，后台 URL 配置成功。
2. 在微信里关注你的测试号（扫码或搜索）。
3. 发 `hello` → 应收到音标/释义/例句/中文。
4. 发 `苹果`（中文）→ 应走中译英查词返回英文卡片。
5. 发 `/stats` → 应收到统计。
6. 若某次查词较慢，应先看到「⏳ 正在查询」，随后收到补推结果。

---

## 八、常见问题

| 现象 | 原因 / 解决 |
|------|------------|
| 后台提交 URL 提示「验证失败」 | Token 与 `.env` 不一致；或本地 Flask 未启动 / ngrok 未通 / 路径非 `/wechat` |
| 配置成功但收不到回复 | 看服务器日志 `[wechat]` 有无异常；确认 `WECHAT_CHANNEL=official` |
| 慢查询后无补推 | `MP_APPID`/`MP_APPSECRET` 未填或错误；或 access_token 获取失败（看日志） |
| 启用服务器配置后原自动回复失效 | 正常，公众号消息改由本程序接管 |
| 想切回个人微信 | `.env` 设 `WECHAT_CHANNEL=personal`，用 cc-weixin 桥接 `/webhook` |
