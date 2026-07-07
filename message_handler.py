"""
message_handler.py — 消息处理模块

接收来自微信（经 cc-weixin 转发到 Flask /webhook）的文本消息，并分发处理：
- "/stats" 或 "统计"  → 统计查询
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
        return "请输入英文单词，或发送 /stats 查看统计。"

    # 统计查询
    if text.lower() in ("/stats", "统计"):
        return _build_stats()

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
