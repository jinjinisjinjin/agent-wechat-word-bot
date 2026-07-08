"""
wechat_official.py — 微信公众号（测试号 / 订阅号）接入模块

职责：
1. 公众号回调接入验证（GET）：校验 signature / timestamp / nonce / echostr
2. 接收用户消息（POST，XML 明文模式）
3. 被动回复（必须在 5 秒内返回 XML）
4. 异步客服消息推送（查词较慢时，先被动回复“查询中”，再用客服消息补推结果）
5. access_token 获取与缓存（2 小时有效，避免频繁请求）

参考微信官方文档「接收消息」「客服消息」接口。

注意：
- 明文模式下 EncodingAESKey 用不到；切换到安全/兼容模式才需要，届时会用 MP_AESKEY。
- 客服消息接口要求用户在 48 小时内与公众号互动过，刚发消息即处于窗口内，可正常推送。
"""
import os
import time
import hashlib
import json
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

# ===== 配置（从环境变量读取，不硬编码）=====
MP_TOKEN = os.environ.get("MP_TOKEN", "")
MP_APPID = os.environ.get("MP_APPID", "")
MP_APPSECRET = os.environ.get("MP_APPSECRET", "")
# 回调路径（需与公众号后台填写的 URL 路径一致）
MP_CALLBACK_PATH = os.environ.get("MP_CALLBACK_PATH", "/wechat")

_BASE = os.path.dirname(os.path.abspath(__file__))
# 云端（腾讯云 SCF 等）只有 /tmp 可写，用 DATA_DIR 重定向持久化文件；
# 本地不设置 DATA_DIR 时退回到代码目录（与原行为一致）。
_DATA_DIR = os.environ.get("DATA_DIR", _BASE)

# access_token 缓存（内存 + 文件，避免每次请求都去换）
_access_token = None
_access_token_expire = 0
_token_cache_file = os.path.join(_DATA_DIR, "mp_token.json")
_token_lock = threading.Lock()

# 已互动用户 OpenID 记录（供定时任务主动推送，如每日复习 / 周报）
_subscribers_file = os.path.join(_DATA_DIR, "mp_subscribers.json")
_subs_lock = threading.Lock()

# 客服消息权限标记：未认证订阅号等无权限的账号，命中一次后自动停用主动推送，避免每日刷屏报错
_custom_msg_disabled = False
_custom_msg_noticed = False

# 消息去重（微信可能重复投递）
_seen_msgids = set()
_seen_lock = threading.Lock()

# 复用 TCP/TLS 连接
_session = requests.Session()
_session.headers.update({"User-Agent": "wechat-word-bot/1.0"})

# 异步任务线程池（处理超时降级 + 客服消息补推）
_executor = ThreadPoolExecutor(max_workers=4)


# ===================== 接入验证（GET）=====================
def verify_signature(signature, timestamp, nonce, token=None):
    """微信回调签名校验（明文 / 兼容模式通用）。

    算法：将 token、timestamp、nonce 三个参数按字典序排序后拼接，
    做 SHA1 哈希，与微信传来的 signature 比对。
    """
    token = token or MP_TOKEN
    if not token:
        return False
    items = sorted([token, timestamp, nonce])
    sha = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    return sha == signature


def verify_get(signature, timestamp, nonce, echostr):
    """GET 接入验证：校验通过返回 echostr（原样回显），否则返回空。"""
    token = MP_TOKEN
    # 计算期望的签名（用于调试对比）
    items = sorted([token or "", timestamp or "", nonce or ""])
    expected = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
    ok = (expected == signature) if token else False

    print(f"[wechat_verify] ===== 微信验证请求详情 =====", flush=True)
    print(f"[wechat_verify]   signature(收到) = {signature}", flush=True)
    print(f"[wechat_verify]   signature(期望) = {expected}", flush=True)
    print(f"[wechat_verify]   timestamp       = {timestamp}", flush=True)
    print(f"[wechat_verify]   nonce           = {nonce}", flush=True)
    print(f"[wechat_verify]   echostr         = {echostr}", flush=True)
    print(f"[wechat_verify]   MP_TOKEN        = {token}", flush=True)
    print(f"[wechat_verify] 校验结果={'✅ 通过' if ok else '❌ 失败'}", flush=True)

    # 写文件日志，方便事后排查（即使终端看不清也能读）
    try:
        log_line = (
            f"\n{'='*50}\n[微信验证] 时间={time.strftime('%H:%M:%S')}\n"
            f"  signature(收到)= {signature}\n"
            f"  signature(期望)= {expected}\n"
            f"  timestamp      = {timestamp}\n"
            f"  nonce          = {nonce}\n"
            f"  echostr        = {echostr}\n"
            f"  MP_TOKEN       = {token}\n"
            f"  校验结果        = {'通过' if ok else '失败'}\n"
            f"{'='*50}\n"
        )
        with open(os.path.join(_DATA_DIR, "wechat_verify.log"), "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass

    if ok:
        return echostr
    return ""


# ===================== access_token =====================
def _load_token_cache():
    """从文件恢复 access_token（进程重启后仍有效）。"""
    global _access_token, _access_token_expire
    try:
        with open(_token_cache_file, encoding="utf-8") as f:
            d = json.load(f)
            _access_token = d.get("access_token")
            _access_token_expire = d.get("expire_at", 0)
    except Exception:
        pass


def _save_token_cache():
    try:
        with open(_token_cache_file, "w", encoding="utf-8") as f:
            json.dump(
                {"access_token": _access_token, "expire_at": _access_token_expire}, f
            )
    except Exception:
        pass


def get_access_token():
    """获取 access_token（带缓存，提前 5 分钟刷新）。失败返回 None。"""
    global _access_token, _access_token_expire
    with _token_lock:
        now = time.time()
        # 内存中仍有效
        if _access_token and now < _access_token_expire - 300:
            return _access_token
        # 尝试从文件恢复
        if not _access_token:
            _load_token_cache()
            if _access_token and now < _access_token_expire - 300:
                return _access_token
        if not MP_APPID or not MP_APPSECRET:
            print("[wechat_official] 缺少 MP_APPID / MP_APPSECRET，无法获取 access_token")
            return None
        try:
            r = _session.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": MP_APPID,
                    "secret": MP_APPSECRET,
                },
                timeout=10,
            )
            data = r.json()
            if "access_token" in data:
                _access_token = data["access_token"]
                _access_token_expire = now + int(data.get("expires_in", 7200))
                _save_token_cache()
                return _access_token
            print(f"[wechat_official] 获取 access_token 失败: {data}")
            return None
        except Exception as e:
            print(f"[wechat_official] 获取 access_token 异常: {e}")
            return None


def send_custom_message(openid, content):
    """通过客服消息接口主动推送文本。需用户在 48 小时内互动过。返回是否成功。

    注意：未认证订阅号等无「客服消息」权限的账号，微信会返回 errcode 48001/43004。
    一旦命中即永久停用主动推送（_custom_msg_disabled），避免每日定时任务刷屏报错。
    """
    global _custom_msg_disabled, _custom_msg_noticed
    if _custom_msg_disabled:
        return False
    token = get_access_token()
    if not token:
        return False
    try:
        r = _session.post(
            "https://api.weixin.qq.com/cgi-bin/message/custom/send",
            params={"access_token": token},
            json={"touser": openid, "msgtype": "text", "text": {"content": content}},
            timeout=10,
        )
        data = r.json()
        if data.get("errcode", 0) == 0:
            return True
        # 无权限类错误：未认证订阅号常见 48001(api unauthorized) / 43004(需关注) / 48002
        if data.get("errcode") in (48001, 43004, 48002):
            _custom_msg_disabled = True
            if not _custom_msg_noticed:
                _custom_msg_noticed = True
                print(
                    "[wechat_official] ⚠️ 当前公众号无「客服消息」权限（多为未认证订阅号），"
                    "主动推送（每日复习/周报）已自动停用。\n"
                    "   如需启用：将公众号认证(300元/年)或改用服务号，并确认 appID/appsecret 正确。",
                    flush=True,
                )
            return False
        print(f"[wechat_official] 客服消息发送失败: {data}")
        return False
    except Exception as e:
        print(f"[wechat_official] 客服消息异常: {e}")
        return False


# ===================== XML 解析 / 封装 =====================
def parse_xml(xml_str):
    """将微信 POST 的 XML 解析为字典（仅取文本子节点）。"""
    root = ET.fromstring(xml_str)
    return {child.tag: (child.text or "") for child in root}


def build_text_reply(from_user, to_user, content):
    """构造被动回复 XML。

    注意：回复时 FromUserName / ToUserName 必须互换——
    用户发来的 FromUserName（OpenID）变成回复的 ToUserName，
    公众号原始 ID 变成回复的 FromUserName。
    """
    ts = int(time.time())
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{ts}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        "</xml>"
    )


# ===================== 订阅者记录 / 去重 =====================
def _record_subscriber(openid):
    if not openid:
        return
    with _subs_lock:
        try:
            subs = set(json.load(open(_subscribers_file, encoding="utf-8")))
        except Exception:
            subs = set()
        if openid not in subs:
            subs.add(openid)
            json.dump(list(subs), open(_subscribers_file, "w", encoding="utf-8"))


def get_subscribers():
    """返回所有互动过的用户 OpenID 列表（供定时主动推送）。"""
    try:
        return json.load(open(_subscribers_file, encoding="utf-8"))
    except Exception:
        return []


def _is_duplicate(msgid):
    if not msgid:
        return False
    with _seen_lock:
        if msgid in _seen_msgids:
            return True
        _seen_msgids.add(msgid)
        if len(_seen_msgids) > 2000:  # 简单清理，避免无限增长
            _seen_msgids.clear()
        return False


# ===================== 消息处理主入口 =====================
def handle_update(xml_str):
    """处理公众号 POST 消息，返回回复文本（XML 字符串 或 "success"）。

    逻辑：
    - 解析 XML，记录订阅者，处理关注事件
    - 文本消息：尝试同步处理（4 秒超时）；
        能在 5 秒内完成 → 直接被动回复（快路径，体验最佳）
        超时 → 先被动回复“查询中”，原任务完成后用客服消息补推真实结果
    """
    import message_handler  # 延迟导入，避免与 main 的循环依赖

    data = parse_xml(xml_str)
    msg_type = data.get("MsgType", "")
    openid = data.get("FromUserName", "")
    self_id = data.get("ToUserName", "")  # 公众号原始 ID
    msg_id = data.get("MsgId", "")

    _record_subscriber(openid)

    # 事件消息（关注 / 取关等）
    if msg_type == "event":
        event = (data.get("Event") or "").lower()
        if event == "subscribe":
            welcome = (
                "👋 你来啦！\n"
                "欢迎来到jinjin的公众号，我很久没有写公众号了，编辑欢迎语的时候我估计未来也就是一些随笔。\n"
                "\n"
                "我顺手写了个单词bot在里面，大致就是查词- agent 保存-形成词库-按艾宾浩斯遗忘曲线给用户发消息提醒。本意是想实现提醒我看看单词，奈何经费有限，还是没有买云服务器，所以没有办法进行每日推送。\n"
                "如果你发英文单词给我回复的是释义，那说明我电脑在线。\n"
                "想知道自己查了多少词？发“我学了啥”（当然也是电脑在线的前提下）。\n"
                "可能会长期不在线hhh\n"
                "这个最早是个微信对话的bot，如果有兴趣可以下载到自己的电脑上部署，发“我要代码”即可获取。\n"
                "\n"
                "总之，欢迎你关注！"
            )
            return build_text_reply(self_id, openid, welcome)
        return "success"  # 其他事件不回复

    if msg_type != "text":
        return build_text_reply(self_id, openid, "暂仅支持文本消息。")

    # 消息去重，防止微信重复投递导致重复回复
    if _is_duplicate(msg_id):
        return "success"

    text = (data.get("Content") or "").strip()
    if not text:
        return "success"

    # 提交查词任务，最多等 4 秒（预留 1 秒网络余量，满足 5 秒限制）
    future = _executor.submit(message_handler.handle_text, openid, text)
    try:
        result = future.result(timeout=4)
        return build_text_reply(self_id, openid, result)
    except Exception:
        # 超时或异常：先被动回复提示，复用同一 future 完成后异步补推
        def _after():
            try:
                res = future.result()  # 复用原任务，不重复计算
                send_custom_message(openid, res)
            except Exception as e:
                print(f"[wechat_official] 异步补推异常: {e}")

        _executor.submit(_after)
        return build_text_reply(self_id, openid, "⏳ 正在查询，请稍候...")


def push_to_all(text):
    """向所有互动过的用户主动推送（供 scheduler 每日复习 / 周报调用）。"""
    global _custom_msg_disabled, _custom_msg_noticed
    if _custom_msg_disabled:
        if not _custom_msg_noticed:
            _custom_msg_noticed = True
            print(
                "[wechat_official] ⚠️ 主动推送已停用：当前公众号无「客服消息」权限"
                "（多为未认证订阅号）。每日复习/周报将不会发送。",
                flush=True,
            )
        return 0
    ok = 0
    for openid in get_subscribers():
        if send_custom_message(openid, text):
            ok += 1
    return ok
