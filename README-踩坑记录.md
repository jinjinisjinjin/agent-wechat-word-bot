# WeChat 单词机器人 · 部署与踩坑记录

> 记录从本地运行到腾讯云 SCF 上云全过程踩过的坑，供复用。

## 项目结构
- 仓库：`jinjinisjinjin/agent-wechat-word-bot`
- 三通道：
  - **微信版**：本机 + `cc-weixin-bridge` 扫码登录
  - **公众号版**：本机运行 `main.py`
  - **公众号云版**：腾讯云 SCF Web 函数 7×24 在线
- Release v1.0.0 三个 zip：`WeChat-word-bot.zip`（微信版）/ `WeChat-word-bot-official.zip`（公众号版，剔除桥接）/ `WeChat-word-bot-cloud.zip`（云端版）
- 公众号欢迎语为随笔风文案，「我要代码」触发词回复 Release 下载地址

## 微信公众平台机制（先搞懂这个）
- 启用「服务器配置」后，公众号后台的自动回复（含被关注/关注回复）**全部失效**。消息二选一：要么给机器人，要么给后台。
- 因此"不受本机开关影响的自动欢迎语"必须让机器人 7×24 在线 → 上云。

## 踩坑清单
1. 打包的 zip 是**源码安装包**，不是"部署到公众号"；真正跑在本机 `python main.py`。
2. 打包必须排除 `.env`、日志、用户数据，防密钥泄露。
3. 隧道演进：ngrok 中国被墙 → 换 natapp 内网穿透 → 最终上云 SCF（免费、稳定）。
4. 本机 `main.py` 退出即无欢迎语（后台已失效 + 本机机器人没跑）。
5. SCF 创建函数**别选「Flask 框架模板」**，会进 Cloud Studio 在线 IDE，找不到上传 zip 入口。正确：从头开始 + Web 函数 + 本地上传 ZIP。
6. 环境变量导入：JSON 数组格式报错 → 改用多行 key-value 粘贴（`WECHAT_CHANNEL` / `MP_TOKEN` / `MP_APPID` / `MP_APPSECRET` / `MP_CALLBACK_PATH`）。
7. API 网关触发器 2025-06-30 起停售新用户 → 改用「函数 URL」开启公网访问。
8. SCF Python 3.9 自带 pip 是坏的（`No module named 'pip._internal.operations.build'`）→ 不能云端 `pip install`。改为预装 **cp39-manylinux** wheel 进 `lib/`，`scf_bootstrap` 里 `export PYTHONPATH=/var/user/lib`。
9. SCF Python 3.9 自带 OpenSSL 1.0.2k，urllib3 v2 需要 ≥1.1.1 → 降级 `urllib3<2`（如 1.26.20）。
10. Web 函数监听 **9000** 端口；仅 `/tmp` 可写 → `DATA_DIR=/tmp`，所有数据文件路径改读 `DATA_DIR` 环境变量。
11. `scf_bootstrap` 要点：LF 换行、`chmod 755`、设 `PORT=9000`/`DATA_DIR=/tmp`/`PYTHONPATH`，最后 `exec python main.py`（不要 pip install）。
12. 密钥安全：不要把真实 `.env` 提交进 git 历史。如已泄露，重置 AppSecret + 换 MP_TOKEN。轮换顺序：**先改云端环境变量并部署 → 再改公众号后台服务器配置 Token**，反了微信验证失败。轮换无需重传 zip（密钥走环境变量）。

## 云端部署快速检查表
- [ ] 创建方式：从头开始 + Web 函数 + 本地上传 ZIP
- [ ] 环境变量：`WECHAT_CHANNEL=official` / `MP_APPID` / `MP_APPSECRET` / `MP_TOKEN` / `MP_CALLBACK_PATH=/wechat` / `PORT=9000` / `DATA_DIR=/tmp` / `PYTHONPATH=/var/user/lib`
- [ ] 函数 URL 开启公网
- [ ] 公众号后台服务器配置：URL = 函数 URL + `/wechat`，Token = 环境变量 `MP_TOKEN`，明文模式

## 相关
- 完整避坑 skill：`tencent-scf-flask-deploy`（WorkBuddy 内部，含建函数/预装依赖/scf_bootstrap/函数 URL/密钥轮换全流程）
