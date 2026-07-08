#!/bin/bash
# install-ngrok.sh — 一键安装 ngrok（macOS ARM）
set -e

echo ">>> 正在下载 ngrok ..."

# ngrok 官方 macOS ARM64 安装包
curl -fsSL https://bin.equinox.io/c/bNyj1mQVY4cng/ngrok-v3-stable-darwin-arm64.tgz -o /tmp/ngrok.tgz

if [ ! -f /tmp/ngrok.tgz ] || [ "$(file -b --mime-type /tmp/ngrok.tgz)" = "text/plain" ]; then
    # 备用方案：尝试 zip 格式（新版）
    curl -fsSL "https://bin.equinox.io/c/bNyj1mQVY4cng/ngrok-v3-stable-darwin-arm64.zip" -o /tmp/ngrok.zip 2>/dev/null || true
    if [ -f /tmp/ngrok.zip ] && [ "$(file -b --mime-type /tmp/ngrok.zip)" = "application/zip" ]; then
        cd /tmp && unzip -o ngrok.zip && rm ngrok.zip
    else
        echo ""
        echo "!!! 自动下载失败，请手动安装 ngrok："
        echo ""
        echo "方法 A（推荐）：打开浏览器访问"
        echo "   https://dashboard.ngrok.com/get-started/setup/macos"
        echo "   下载 macOS Apple Silicon 版本，解压后放到 /usr/local/bin/"
        echo ""
        echo "方法 B：如果你有 Homebrew，运行"
        echo "   brew install ngrok"
        echo ""
        exit 1
    fi
else
    tar -xzf /tmp/ngrok.tgz -C /tmp/
    rm /tmp/ngrok.tgz
fi

# 安装到 PATH（需要管理员权限）
if [ -w /usr/local/bin ]; then
    mv /tmp/ngrok /usr/local/bin/ngrok
else
    echo "需要输入密码以将 ngrok 安装到 /usr/local/bin/"
    sudo mv /tmp/ngrok /usr/local/bin/ngrok
fi

chmod +x /usr/local/bin/ngrok

echo ""
echo ">>> 安装成功！版本信息："
/usr/local/bin/ngrok version
echo ""
echo ">>> 使用方法：新开一个终端窗口，运行："
echo "    ngrok http 9090"
echo ">>> 然后把输出的 Forwarding 地址（https://xxx.ngrok-free.app）填到公众号测试号后台"
