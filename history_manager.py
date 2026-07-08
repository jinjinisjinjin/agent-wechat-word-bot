"""
history_manager.py — 单词数据管理模块

负责单词历史记录的读写，数据存储在 ~/word_history.json（UTF-8，中文不转义）。

每条记录字段如下：
{
    "word": "apple",                # 原始单词
    "phonetic": "/ˈæpl/",           # 音标
    "meaning": "苹果",              # 综合英文释义（多个词性释义用「；」拼接）
    "meaning_zh": "苹果",           # 综合中文释义（用于测验选项，避免中英混排）
    "examples": ["例句1", ...],     # 例句列表
    "synonyms": ["syn1", ...],      # 同义词列表
    "meanings_detail": [            # 结构化释义（含中文），用于免联网复用
        {"partOfSpeech": "n", "definition": "苹果", "example": "...", "zh": "苹果"}
    ],
    "query_count": 1,               # 累计查询次数
    "added_date": "2026-07-08",     # 首次添加日期（用于周报“新增词数”统计）
    "review_dates": [               # 5 个复习日期（当天 +1/+2/+4/+7/+15 天）
        "2026-07-09", "2026-07-10", "2026-07-12", "2026-07-15", "2026-07-23"
    ],
    "next_review_index": 0          # 下一次应复习的复习日期下标（达到 5 表示全部完成）
}
"""
import json
import os
from datetime import datetime, timedelta

# 数据文件路径：默认用户主目录下的 word_history.json
# 云端（腾讯云 SCF 等）只有 /tmp 可写，可通过环境变量 DATA_DIR 重定向
_DATA_DIR = os.environ.get("DATA_DIR")
if _DATA_DIR:
    DATA_FILE = os.path.join(_DATA_DIR, "word_history.json")
else:
    DATA_FILE = os.path.expanduser("~/word_history.json")

# 复习间隔（天）：第 1、2、4、7、15 天
REVIEW_INTERVALS = [1, 2, 4, 7, 15]


def _today_str():
    """返回今天日期字符串（YYYY-MM-DD）。"""
    return datetime.now().strftime("%Y-%m-%d")


def _load():
    """读取 JSON 文件，返回单词列表；文件不存在或解析失败返回空列表。"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[history_manager] 读取数据失败，返回空列表：", e)
        return []


def _save(words):
    """将单词列表写回 JSON 文件（中文不转义、缩进 2 空格）。"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)


def _build_review_dates(start_date):
    """根据起始日期，生成 5 个复习日期（start + 1/2/4/7/15 天）。"""
    base = datetime.strptime(start_date, "%Y-%m-%d")
    return [(base + timedelta(days=d)).strftime("%Y-%m-%d") for d in REVIEW_INTERVALS]


def save_word(word_data):
    """保存或更新单词。

    - 若单词已存在（大小写不敏感）：仅将 query_count + 1，不重置复习计划。
    - 若为新单词：写入完整记录，并生成 5 个复习日期。
    """
    words = _load()
    word = word_data["word"].strip().lower()
    for w in words:
        if w["word"].lower() == word:
            w["query_count"] = w.get("query_count", 0) + 1
            _save(words)
            return
    today = _today_str()
    detail = word_data.get("meanings_detail", [])
    meaning = word_data.get("meaning", "")
    meaning_zh = word_data.get("meaning_zh", "")
    # 若未显式给中文综合释义，则从结构化释义里汇总
    if not meaning_zh and detail:
        meaning_zh = "；".join(m.get("zh", "") for m in detail if m.get("zh")) or ""
    record = {
        "word": word_data["word"].strip(),
        "phonetic": word_data.get("phonetic", ""),
        "meaning": meaning,
        "meaning_zh": meaning_zh,
        "examples": word_data.get("examples", []),
        "synonyms": word_data.get("synonyms", []),
        "meanings_detail": detail,
        "query_count": 1,
        "added_date": today,                       # 首次添加日期
        "review_dates": _build_review_dates(today),
        "next_review_index": 0,
    }
    words.append(record)
    _save(words)


def get_word(word):
    """根据单词返回记录 dict（大小写不敏感），不存在返回 None。"""
    word = word.strip().lower()
    for w in _load():
        if w["word"].lower() == word:
            return w
    return None


def get_all_words():
    """返回所有单词记录列表。"""
    return _load()


def get_due_words(today_date):
    """返回今天到期的待复习单词列表。

    判定条件：next_review_index < 5 且 review_dates[next_review_index] == today_date。
    """
    due = []
    for w in _load():
        idx = w.get("next_review_index", 0)
        dates = w.get("review_dates", [])
        if idx < 5 and idx < len(dates) and dates[idx] == today_date:
            due.append(w)
    return due


def mark_reviewed(word):
    """将指定单词的 next_review_index 加 1（封顶为 5，表示全部复习完成）。"""
    words = _load()
    for w in words:
        if w["word"].lower() == word.strip().lower():
            w["next_review_index"] = min(w.get("next_review_index", 0) + 1, 5)
            _save(words)
            return


def get_total_words():
    """返回总词数。"""
    return len(_load())


def get_pending_review_count():
    """返回 next_review_index < 5 的待复习单词数量。"""
    return sum(1 for w in _load() if w.get("next_review_index", 0) < 5)


def get_top_words(n=3):
    """返回查询次数最高的 Top n 单词，格式 [(word, count), ...]。"""
    words = _load()
    top = sorted(words, key=lambda w: w.get("query_count", 0), reverse=True)[:n]
    return [(w["word"], w.get("query_count", 0)) for w in top]


def get_weekly_stats(start_date, end_date):
    """返回一段时间内的统计。

    返回 dict：
    {
        "new_words": int,    # 区间内首次添加的单词数
        "reviews_done": int, # 区间内已完成（复习日期落在区间内且已推进）的复习次数
        "top_words": [...]   # 热词 Top3（基于 query_count 全量近似）
    }
    """
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")
    new_words = 0
    reviews_done = 0
    for w in _load():
        # 新增词数：added_date 落在区间内
        added = w.get("added_date")
        if added:
            try:
                if s <= datetime.strptime(added, "%Y-%m-%d") <= e:
                    new_words += 1
            except Exception:
                pass
        # 完成复习数：复习日期落在区间内，且该次复习已完成（下标 < next_review_index）
        idx = w.get("next_review_index", 0)
        for i, d in enumerate(w.get("review_dates", [])):
            if i < idx:
                try:
                    if s <= datetime.strptime(d, "%Y-%m-%d") <= e:
                        reviews_done += 1
                except Exception:
                    pass
    return {
        "new_words": new_words,
        "reviews_done": reviews_done,
        "top_words": get_top_words(3),
    }
