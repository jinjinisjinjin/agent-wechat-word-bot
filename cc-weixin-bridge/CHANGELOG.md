# 更新日志

## 0.2.0

- 每个微信用户独立会话上下文，支持多轮对话记忆（基于 session resume）
- 专用工作区 `~/.cc-weixin/workspace/`，不再污染项目目录
- 新增调试日志支持（`DEBUG=cc-weixin:*`）
- 新增 `debug` 依赖

## 0.1.1

- 用截图替换 ASCII art 演示图

## 0.1.0

- TUI 界面（基于 Ink，默认模式）
- iTerm2 下二维码以图片形式渲染
- 重命名为 cc-weixin，发布到 npm
- 接入 Claude Agent SDK 实现自动回复
- iLink Bot API 长轮询收发消息
- 微信扫码登录
