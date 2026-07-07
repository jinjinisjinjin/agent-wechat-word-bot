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
from flask import Flask, request, jsonify

import history_manager
import message_handler
import scheduler

def _load_dotenv():
    """极简 .env 加载（不引入额外依赖），仅设置尚未存在的环境变量。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

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

    注意：当前为本地占位实现（打印到控制台）。
    在第四步接入 cc-weixin 后，可在此调用 cc-weixin 提供的发送接口，
    例如通过本地 HTTP 调用 cc-weixin 的推送端点。
    """
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
