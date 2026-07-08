#!/usr/bin/env python3
"""通过 ngrok 公网地址测试微信验证（使用真实签名）。"""
import hashlib, time, urllib.request, urllib.parse, os

_env = os.path.join("/Users/zhuangjin/wechat-word-bot", ".env")
MP_TOKEN = ""
for line in open(_env, encoding="utf-8"):
    line = line.strip()
    if line.startswith("MP_TOKEN="):
        MP_TOKEN = line.split("=", 1)[1].strip()

ts = str(int(time.time()))
nonce = "testnonce123"
sig = hashlib.sha1("".join(sorted([MP_TOKEN, ts, nonce])).encode()).hexdigest()
params = urllib.parse.urlencode({"signature": sig, "timestamp": ts, "nonce": nonce, "echostr": "ECHO_OK_999"})
url = f"https://endurance-tastiness-magnetize.ngrok-free.dev/wechat?{params}"

print(f"测试公网地址: {url[:70]}...")
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        body = r.read().decode()
        print(f"HTTP {r.status}, 返回: {body!r}")
        if body == "ECHO_OK_999":
            print("\n✅ 公网链路完全通！微信应该能配置成功")
        else:
            print("\n❌ 公网返回异常")
except Exception as e:
    print(f"\n❌ 公网测试失败: {e}")
