"""
main.py — 主入口

功能：
1. 启动时确保 ~/word_history.json 存在（不存在则创建空 JSON 数组）。
2. 启动定时任务（后台线程，每天 08:00 复习推送 / 每周一 08:30 周报）。
3. 启动 Flask 服务，提供 /webhook 路由接收 cc-weixin 转发的消息。

接入方式（方式 b）：
- cc-weixin 将收到的微信消息以 POST JSON 形式发到 http://localhost:5000/webhook
- 本服务解析 JSON，调用 message_handler 处理，并返回 {"reply": "..."} 供 cc-weixin 回显
- 定时任务的主动推送通过 scheduler.set_sender 注入的 send_weixin 完成
"""
import os
import json
import threading
from flask import Flask, request, jsonify, Response


def _load_dotenv():
    """极简 .env 加载（不引入额外依赖），仅设置尚未存在的环境变量。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    print(f"[env_debug] 正在加载 .env，路径={p}，存在={os.path.exists(p)}", flush=True)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
        print(f"[env_debug] .env 加载完成，MP_TOKEN={'✅ ' + os.environ.get('MP_TOKEN', '')[:8] + '...' if os.environ.get('MP_TOKEN') else '❌'}", flush=True)


# ⚠️ 必须在 import wechat_official 之前加载 .env，否则模块级变量 MP_TOKEN 为空！
_load_dotenv()

import history_manager
import message_handler
import scheduler
import wechat_official

app = Flask(__name__)
HISTORY_FILE = history_manager.DATA_FILE
# 端口可被环境变量 PORT 覆盖（支持 .env），默认 9090（避开 macOS 系统占用）
# 注：macOS 的 ControlCenter 占用了 5000 端口（AirPlay），故默认避开
PORT = int(os.environ.get("PORT", "9090"))


def ensure_history_file():
    """若历史文件不存在则创建空 JSON 数组。"""
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)


def send_weixin(text):
    """向微信发送消息（主动推送，如每日复习 / 周报）。

    通道由环境变量 WECHAT_CHANNEL 决定：
    - personal（默认）：cc-weixin 个人微信，当前为占位打印（cc-weixin 桥接走 /webhook 被动收发）
    - official：微信公众号，通过客服消息接口推送给所有互动过的用户
    """
    channel = os.environ.get("WECHAT_CHANNEL", "personal")
    if channel == "official":
        sent = wechat_official.push_to_all(text)
        print(f"[weixin] 公众号客服消息已推送 {sent} 人")
    else:
        print("[weixin] 待发送消息：\n" + text)


# 将发送器注入 scheduler，供定时任务使用
scheduler.set_sender(send_weixin)


def _extract_message(data):
    """从 cc-weixin 的 webhook JSON 中尽力提取 (user_id, text)。

    兼容多种常见字段命名，避免 cc-weixin 字段变动导致解析失败。
    """
    if isinstance(data, dict):
        text = (data.get("message") or data.get("text") or data.get("content")
                or data.get("Msg") or "").strip()
        user_id = (data.get("from") or data.get("user") or data.get("sender")
                   or data.get("userId") or data.get("FromUserName") or "unknown")
        return user_id, text
    return "unknown", str(data)


@app.route("/webhook", methods=["POST"])
def webhook():
    """接收 cc-weixin 转发的消息，处理并返回回复内容。"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_id, text = _extract_message(data)
        if not text:
            return jsonify({"status": "ok", "reply": ""})
        reply = message_handler.handle_text(user_id, text)
        return jsonify({"status": "ok", "reply": reply})
    except Exception as e:
        print(f"[webhook] 内部错误: {e}", flush=True)
        return jsonify({"status": "error", "reply": f"⚠️ 机器人内部错误：{str(e)}"}), 500


@app.route("/wechat", methods=["GET", "POST"])
def wechat_official_endpoint():
    """微信公众号回调入口（测试号 / 订阅号）。

    GET：微信服务器接入验证（Token 校验），返回 echostr 完成握手。
    POST：接收用户消息（XML 明文模式），处理后返回 XML 被动回复。
    """
    if request.method == "GET":
        signature = request.args.get("signature", "")
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        echostr = request.args.get("echostr", "")
        return wechat_official.verify_get(signature, timestamp, nonce, echostr)

    # POST：接收并回复用户消息
    try:
        xml_str = request.get_data(as_text=True)
        reply = wechat_official.handle_update(xml_str)
        # 空回复或 "success" 表示不回复；否则返回 XML（指定 text/xml 避免微信解析失败）
        if reply in ("", "success"):
            return Response(reply, mimetype="text/plain")
        return Response(reply, mimetype="text/xml")
    except Exception as e:
        print(f"[wechat] 处理异常: {e}", flush=True)
        # 任何异常都必须返回 success，否则微信会重试
        return Response("success", mimetype="text/plain")


@app.route("/", methods=["GET"])
def index():
    return "wechat-word-bot is running."


if __name__ == "__main__":
    ensure_history_file()
    # 启动定时任务（后台线程）
    scheduler.run_scheduler()
    # 启动 Flask 服务
    # threaded=True：多个消息并发处理，互不打断
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
