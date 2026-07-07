#!/bin/sh
# 微信单词机器人 —— 一键启动脚本（macOS / Linux）
# 功能：安装依赖 → 启动 Flask(webhook) → 启动 cc-weixin 桥接（需扫码登录）

cd "$(dirname "$0")"
echo "📦 安装 Python 依赖..."
pip3 install -r requirements.txt 2>/dev/null || true

echo "🚀 启动 Flask 服务 (http://localhost:9090) ..."
python3 main.py &
FLASK_PID=$!

sleep 2

echo "🤖 启动 cc-weixin 桥接（首次请用微信扫码登录）..."
cd cc-weixin-bridge
if [ ! -d "node_modules" ]; then
    echo "   正在安装桥接依赖..."
    npm install
fi
node cc-weixin.mjs

echo ""
echo "⏹ 桥接已退出，正在清理 Flask 进程..."
kill "$FLASK_PID" 2>/dev/null || true
