"""
word_service.py — 查词服务模块

调用 Free Dictionary API 查询英文单词的音标、释义、例句、同义词，
并补充中文释义（多源翻译：MyMemory 优先，Google 兜底；均免 API Key）。
支持「中文查词」：先把中文翻译成英文，再用英文去查词典。
API 文档：https://dictionaryapi.dev/

性能优化：
1. requests.Session() 复用 TCP/TLS 连接
2. 内存缓存 _cache：已查过的词直接命中（零网络）
3. 线程池并发翻译多条释义
4. 历史命中免联网（由 message_handler 先查本地再调本函数）
"""
import requests
from concurrent.futures import ThreadPoolExecutor

# Free Dictionary API 模板，{word} 为待查单词（小写）
DICTIONARY_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

# 翻译源（按优先级排序，国内网络可访问的放前面）
# 每个源的 params 接受 (q, sl, tl) 三个参数，支持双向翻译
# MyMemory：免费无需 key，国内通常可达
_TRANSLATE_SOURCES = [
    {
        "name": "MyMemory",
        "url": "https://api.mymemory.translated.net/get",
        "params": lambda q, sl, tl: {"q": q, "langpair": f"{sl}|{tl}"},
        "parse": lambda data: data.get("responseData", {}).get("translatedText", ""),
    },
    # Google 翻译作为备选（部分网络环境可达）
    {
        "name": "Google",
        "url": "https://translate.googleapis.com/translate_a/single",
        "params": lambda q, sl, tl: {"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": q},
        "parse": lambda data: "".join(
            seg[0] for seg in (data[0] if isinstance(data, list) else [])
            if seg and seg[0]
        ) if isinstance(data, list) else "",
    },
]

# 请求超时（秒）—— 翻译超时设短，失败快速降级不拖慢整体响应
REQUEST_TIMEOUT = 10
TRANSLATE_TIMEOUT = 2  # 每个翻译源最多等 2 秒

# 单个单词最多展示 / 翻译的释义条数
MAX_MEANINGS = 6

# 复用 TCP/TLS 连接
_session = requests.Session()
_session.headers.update({"User-Agent": "wechat-word-bot/1.0"})

# 内存缓存：单词(小写) -> 查词结果（含中文）
_cache = {}


def _translate(text, sl="en", tl="zh-CN"):
    """翻译：依次尝试多个翻译源，任一成功即返回。全部失败返回空串。

    sl / tl 为源语言 / 目标语言代码，如 "en"、"zh-CN"。
    """
    if not text:
        return ""
    for src in _TRANSLATE_SOURCES:
        try:
            resp = _session.get(
                src["url"],
                params=src["params"](text, sl, tl),
                timeout=TRANSLATE_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            result = src["parse"](data)
            if result and result.strip():
                return result.strip()
        except Exception as e:
            print(f"[word_service] {src['name']} 翻译失败：{e}")
            continue
    return ""


def translate_en_to_zh(text):
    """英文 -> 中文（供释义翻译使用）。"""
    return _translate(text, "en", "zh-CN")


def translate_zh_to_en(text):
    """中文 -> 英文（供中文查词使用）。"""
    return _translate(text, "zh-CN", "en")


def _translate_batch(texts):
    """并发翻译多个文本（英文 -> 中文），保持顺序返回列表。"""
    if not texts:
        return []
    with ThreadPoolExecutor(max_workers=min(len(texts), 6)) as ex:
        return list(ex.map(translate_en_to_zh, texts))


def lookup_word(word):
    """查询单词。

    成功返回结构化 dict：
    {
        "word": str,
        "phonetic": str,
        "meanings": [{"partOfSpeech": str, "definition": str, "example": str, "zh": str}],
        "synonyms": [str, ...]
    }

    失败（单词不存在 / 网络超时 / 解析异常）返回 None。
    """
    key = word.strip().lower()
    # 命中内存缓存，直接返回（最快路径，零网络）
    if key in _cache:
        return _cache[key]
    try:
        url = DICTIONARY_API.format(word=key)
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        # 单词不存在时 API 返回 404
        if resp.status_code == 404:
            print(f"[word_service] 单词未找到：{word}")
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None

        phonetic = ""
        meanings = []
        synonyms = []

        for entry in data:
            # 取第一个可用的音标
            if not phonetic and entry.get("phonetic"):
                phonetic = entry["phonetic"]
            for m in entry.get("meanings", []):
                pos = m.get("partOfSpeech", "")
                for d in m.get("definitions", []):
                    meanings.append({
                        "partOfSpeech": pos,
                        "definition": d.get("definition", ""),
                        "example": d.get("example", ""),
                        "zh": "",  # 稍后并发填充中文
                    })
                    # 汇总同义词（去重）
                    for syn in d.get("synonyms", []):
                        if syn not in synonyms:
                            synonyms.append(syn)
                # 控制条数，避免消息过长、翻译过慢
                if len(meanings) >= MAX_MEANINGS:
                    break
            if len(meanings) >= MAX_MEANINGS:
                break
        meanings = meanings[:MAX_MEANINGS]

        # 并发补充中文释义
        zh_list = _translate_batch([m["definition"] for m in meanings])
        for m, zh in zip(meanings, zh_list):
            m["zh"] = zh

        result = {
            "word": data[0].get("word", word),
            "phonetic": phonetic,
            "meanings": meanings,
            "synonyms": synonyms,
        }
        _cache[key] = result
        return result
    except requests.exceptions.Timeout:
        print("[word_service] 请求超时")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[word_service] 网络错误：{e}")
        return None
    except Exception as e:
        print(f"[word_service] 解析错误：{e}")
        return None
