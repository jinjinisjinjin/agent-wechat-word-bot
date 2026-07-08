"""
message_handler.py — 消息处理模块

接收来自微信（经 cc-weixin 转发到 Flask /webhook）的文本消息，并分发处理：
- "统计"/"进度"/"战绩"/"背了多少"  → 统计查询（多种自然触发）
- 单个字母 A/B/C/D    → 测验答题判断
- 含中文的文本        → 中文查词（先中译英，再用英文查词典）
- 其它文本（英文）    → 查词请求，查词后记录并返回结果
"""
import re
import history_manager
import word_service
import quiz_manager

# 判断文本是否包含中文字符（CJK 统一表意文字区）
_CN_RE = re.compile(r'[一-鿿]')


def _format_word(result):
    """将查词结果格式化为适合微信显示的文本（含中文释义，不含“已记录”提示）。"""
    lines = [f"📖 {result['word']}  {result.get('phonetic', '')}"]
    for i, m in enumerate(result["meanings"], 1):
        lines.append(f"{i}. [{m['partOfSpeech']}] {m['definition']}")
        # 中文释义（新增）
        if m.get("zh"):
            lines.append(f"    中文：{m['zh']}")
        if m.get("example"):
            lines.append(f"    例：{m['example']}")
    syns = result.get("synonyms", [])
    if syns:
        lines.append("同义词：" + "、".join(syns[:8]))
    return "\n".join(lines)


def _format_from_record(rec):
    """用历史记录中的 meanings_detail 直接格式化（免联网，最快路径）。"""
    return _format_word({
        "word": rec.get("word", ""),
        "phonetic": rec.get("phonetic", ""),
        "meanings": rec.get("meanings_detail", []),
        "synonyms": rec.get("synonyms", []),
    })


# 统计查询触发词：保留 /stats 与「统计」，并补充更自然的口语表达
_STATS_EXACT = {
    "/stats", "stats", "统计", "进度", "我的进度",
    "战绩", "成绩", "成绩单", "总结", "回顾",
    "学习情况", "学到了什么", "学习报告", "我学了啥",
}
_STATS_SUBSTR = (
    "背了多少", "记了多少", "学了多少", "掌握多少", "多少词",
    "多少个", "学得怎样", "学得怎么样", "怎么样了", "我的单词",
)


def _is_stats_query(text):
    """判断用户是否想查看学习统计（兼容命令式与自然口语）。"""
    t = text.strip().lower()
    if t in _STATS_EXACT:
        return True
    return any(k in text for k in _STATS_SUBSTR)


def _build_stats():
    """生成统计文本：总词数、待复习数、高频词 Top3。"""
    total = history_manager.get_total_words()
    pending = history_manager.get_pending_review_count()
    top = history_manager.get_top_words(3)
    lines = ["📊 学习统计", f"总词数：{total}", f"待复习：{pending}"]
    if top:
        lines.append("高频词 Top3：")
        for i, (w, c) in enumerate(top, 1):
            lines.append(f"  {i}. {w}（查询 {c} 次）")
    else:
        lines.append("高频词 Top3：暂无")
    return "\n".join(lines)


# 源码/安装指引触发词
_SOURCE_EXACT = {
    "代码", "我要代码", "源码", "项目", "项目地址", "github", "开源",
    "安装", "怎么安装", "如何安装", "怎么部署", "如何部署",
    "自己部署", "自己搭建", "获取代码", "搭建教程",
}
_SOURCE_SUBSTR = ("怎么装", "如何装", "自己装", "自己用", "部署教程", "安装教程")


def _is_source_query(text):
    """判断用户是否想获取源码 / 安装指引。"""
    t = text.strip().lower()
    if t in _SOURCE_EXACT:
        return True
    return any(k in text for k in _SOURCE_SUBSTR)


def _build_source_info():
    """返回源码获取方式与简明安装步骤（微信 / 个人微信版）。"""
    repo = "https://github.com/jinjinisjinjin/agent-wechat-word-bot"
    release_zip = "https://github.com/jinjinisjinjin/agent-wechat-word-bot/releases/download/v1.0.0/WeChat-word-bot.zip"
    steps = [
        "📦 单词机器人 · 开源代码（微信 / 个人微信版）",
        f"一键下载（含全部源码）：{release_zip}",
        f"GitHub 仓库（含完整说明）：{repo}",
        "",
        "本地安装步骤（个人微信）：",
        "1. 下载并解压 WeChat-word-bot.zip",
        "2. 装依赖：pip install -r requirements.txt，再 cd cc-weixin-bridge && npm install",
        "3. 配置：复制 .env.example 为 .env（默认 WECHAT_CHANNEL=personal 即微信）",
        "4. 启动：bash start.sh（终端会打印登录二维码）",
        "5. 手机微信扫码登录，给 Bot 发单词即可开始学习",
        "",
        "💡 公众号接入为可选扩展，详见 WECHAT_OFFICIAL_SETUP.md；默认即为个人微信。",
    ]
    return "\n".join(steps)


def _save_and_reply(result, header=""):
    """把查词结果落盘（记录/更新），并返回格式化回复文本。

    header：可选的引导语（如中文查词时展示「苹果 → apple」）。
    """
    detail = result["meanings"]
    meaning = "；".join(
        f"[{m['partOfSpeech']}] {m['definition']}"
        for m in detail if m.get("definition")
    ) or "（无释义）"
    examples = [m.get("example", "") for m in detail if m.get("example")]

    history_manager.save_word({
        "word": result["word"],
        "phonetic": result.get("phonetic", ""),
        "meaning": meaning,
        "meaning_zh": "；".join(m.get("zh", "") for m in detail if m.get("zh")) or "",
        "examples": examples,
        "synonyms": result.get("synonyms", []),
        "meanings_detail": detail,
    })

    return header + _format_word(result)


def _handle_chinese_query(text):
    """中文查词：先中译英，再用英文查词典。"""
    en = word_service.translate_zh_to_en(text)
    if not en:
        return f"抱歉，暂时无法翻译「{text}」，请稍后重试。"
    # 翻译结果可能含多个候选词或短语，取第一个英文词去查词典
    first_word = re.split(r'[\s,.;，。；、]+', en)[0].strip().lower()
    if not first_word or not first_word.isalpha():
        return f"「{text}」→ 英文：{en}\n（暂无法识别为可查询的英文单词）"

    result = word_service.lookup_word(first_word)
    if result is None:
        return f"「{text}」→ 英文：{en}\n（词典中未找到该词的详细释义）"

    header = f"「{text}」→ {result['word']}\n"
    return _save_and_reply(result, header=header)


def handle_text(user_id, text):
    """处理一条文本消息，返回要回复给用户的字符串。

    user_id：发送者标识（由 cc-weixin 提供，本模块仅透传记录）。
    """
    text = (text or "").strip()
    if not text:
        return "请输入英文单词，或发送「统计」「进度」查看学习情况。"

    # 统计查询（支持自然口语触发，不局限于 /stats）
    if _is_stats_query(text):
        return _build_stats()

    # 源码 / 安装指引
    if _is_source_query(text):
        return _build_source_info()

    # 测验答题（单个字母 A/B/C/D，忽略大小写）
    if len(text) == 1 and text.upper() in ("A", "B", "C", "D"):
        return quiz_manager.check_answer(text)

    # 含中文 → 中文查词（中译英后查词典）
    if _CN_RE.search(text):
        return _handle_chinese_query(text)

    # 英文单词：已查过的词直接复用历史数据，免联网（最快路径）
    key = text.lower()
    existing = history_manager.get_word(key)
    if existing and existing.get("meanings_detail"):
        # 仅累加查询次数，不重置复习计划
        history_manager.save_word({
            "word": existing["word"],
            "phonetic": existing.get("phonetic", ""),
            "meaning": existing.get("meaning", ""),
            "meaning_zh": existing.get("meaning_zh", ""),
            "examples": existing.get("examples", []),
            "synonyms": existing.get("synonyms", []),
            "meanings_detail": existing.get("meanings_detail", []),
        })
        return _format_from_record(existing)

    # 新词：联网查词 + 翻译中文
    result = word_service.lookup_word(text)
    if result is None:
        return f"未找到单词「{text}」或网络异常，请检查拼写后重试。"

    return _save_and_reply(result)
