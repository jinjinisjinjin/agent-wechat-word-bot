#!/bin/sh
# 微信单词机器人 · 一键链路自查 / 重启
# 用法：
#   sh ~/wechat-word-bot/check_tunnel.sh          # 仅自查（不改动任何服务）
#   sh ~/wechat-word-bot/check_tunnel.sh restart  # 杀掉旧进程 → 按正确顺序重启 → 自查
#
# 顺序很重要：必须先启动机器人(main.py)，再启动 natapp，否则隧道连不上本地。

BOT_PORT=9090
PROJECT_DIR="$HOME/wechat-word-bot"
NATAPP_BIN="$HOME/Downloads/natapp"
NATAPP_TOKEN="3b0ff034d334382e"
MP_TOKEN="jZU6MqOdiKd8SVsuNFABcgUAHaI3W603"

# ============ 重启模式 ============
if [ "$1" = "restart" ]; then
    echo ">>> [重启] 清理旧进程..."
    PIDS=$(lsof -ti :$BOT_PORT 2>/dev/null)
    if [ -n "$PIDS" ]; then kill -9 $PIDS 2>/dev/null; fi
    pkill -f "natapp -authtoken" 2>/dev/null
    sleep 1

    echo ">>> [重启] 启动机器人 (后台运行, 日志: bot.log)..."
    cd "$PROJECT_DIR" && nohup python3 main.py > "$PROJECT_DIR/bot.log" 2>&1 &
    sleep 3

    echo ">>> [重启] 启动 natapp 隧道 (后台运行, 日志: natapp.log)..."
    nohup "$NATAPP_BIN" -authtoken="$NATAPP_TOKEN" > "$PROJECT_DIR/natapp.log" 2>&1 &
    sleep 4

    echo ">>> [重启] 完成，开始自查 ↓"
    echo ""
fi

echo "=========================================="
echo "   微信单词机器人 · 链路自查"
echo "=========================================="

# ---------- 1. 机器人（端口 9090）----------
echo ""
echo "[1] 机器人 (端口 $BOT_PORT)"
if lsof -i :$BOT_PORT >/dev/null 2>&1; then
    echo "  ✅ 正在运行 (端口 $BOT_PORT 已监听)"
else
    echo "  ❌ 未运行！请执行："
    echo "     cd $PROJECT_DIR && python3 main.py"
fi

# ---------- 2. natapp 隧道 ----------
echo ""
echo "[2] natapp 隧道"
AUTHTOKEN=$(ps aux | grep -o 'natapp -authtoken=[A-Za-z0-9]*' | head -1 | sed 's/.*authtoken=//')
if [ -z "$AUTHTOKEN" ]; then
    echo "  ❌ 未检测到 natapp 进程！请执行："
    echo "     $NATAPP_BIN -authtoken=$NATAPP_TOKEN"
else
    echo "  ✅ natapp 进程在运行 (authtoken 已读取)"
    # 尝试通过 natapp 官方 API 自动获取当前域名
    DOMAIN=$(curl -s --connect-timeout 8 "https://api.natapp.cn/tunnel/list?authtoken=$AUTHTOKEN" 2>/dev/null \
             | grep -o '"tunnel_domain":"[^"]*"' | head -1 | sed 's/"tunnel_domain":"//;s/"//')
    if [ -n "$DOMAIN" ]; then
        echo "  🌐 当前域名: $DOMAIN"
    else
        echo "  ⚠️  无法自动获取域名，请看 natapp 终端里『Forwarding』那行显示的地址"
    fi
fi

# ---------- 3. 微信后台应填的 URL ----------
echo ""
echo "[3] 微信测试号后台 → 接口配置信息 → 应填："
if [ -n "$DOMAIN" ]; then
    echo "     URL  : $DOMAIN/wechat"
else
    echo "     URL  : <natapp 终端显示的域名>/wechat"
fi
echo "     Token : $MP_TOKEN"
echo "     模式  : 明文模式"

echo ""
echo "=========================================="
echo "   自查完毕"
echo "=========================================="
