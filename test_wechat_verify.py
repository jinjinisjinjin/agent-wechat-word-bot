#!/usr/bin/env python3
"""本地模拟微信验证请求，检查代码逻辑是否正确。"""
import hashlib
import time
import urllib.request
import urllib.parse

# 从 .env 读取 Token（和 main.py 一样的逻辑）
import os
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
MP_TOKEN = ""
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("MP_TOKEN="):
                MP_TOKEN = line.split("=", 1)[1].strip()

print(f"读取到的 MP_TOKEN = {MP_TOKEN[:8]}..." if MP_TOKEN else "MP_TOKEN 未读取到！")

# 模拟微信：用 token/timestamp/nonce 算签名
timestamp = str(int(time.time()))
nonce = "abc123xyz"
items = sorted([MP_TOKEN, timestamp, nonce])
sha = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()

print(f"\n模拟参数：")
print(f"  timestamp = {timestamp}")
print(f"  nonce     = {nonce}")
print(f"  signature = {sha}")

# 拼本地请求
params = urllib.parse.urlencode({
    "signature": sha,
    "timestamp": timestamp,
    "nonce": nonce,
    "echostr": "TEST_ECHOSTR_12345"
})
url = f"http://127.0.0.1:9090/wechat?{params}"

print(f"\n请求: {url[:80]}...")
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print(f"HTTP 状态码: {resp.status}")
        print(f"返回内容: {body!r}")
        if body == "TEST_ECHOSTR_12345":
            print("\n✅ 验证通过！代码逻辑完全正确，问题在微信后台配置或网络侧")
        else:
            print("\n❌ 验证失败！返回内容不是 echostr")
except Exception as e:
    print(f"\n❌ 请求失败: {e}")
