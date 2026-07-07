"""
quiz_manager.py — 测验管理模块

生成词义配对选择题（4 个选项：1 正确 + 3 干扰），校验用户答案并推进复习进度。
当前测验缓存在内存变量 current_quiz 中（单用户场景足够；多用户需改为按 user_id 存储）。
"""
import random
import history_manager

# 当前测验缓存（内存）
current_quiz = {
    "word": "",                       # 题目对应的单词
    "correct": "A",                   # 正确选项字母
    "options": {"A": "", "B": "", "C": "", "D": ""},  # 各选项释义
}

# 历史不足 3 个干扰项时使用的预设基础词释义
FALLBACK_MEANINGS = {
    "easy": "容易的",
    "hard": "困难的",
    "big": "大的",
    "small": "小的",
    "fast": "快的",
    "slow": "慢的",
}

# 选项字母
LETTERS = ["A", "B", "C", "D"]


def generate_quiz(word):
    """为指定单词生成一道选择题，返回题目字符串并缓存 current_quiz。

    干扰项来源：从所有历史单词释义中随机选 3 个不同释义；
    若历史不足，用 FALLBACK_MEANINGS 补足。
    """
    rec = history_manager.get_word(word)
    if not rec:
        return "未找到该单词的释义，无法生成测验。"

    # 优先使用中文释义，避免选项里中英混排
    correct_meaning = rec.get("meaning_zh") or rec.get("meaning", "")

    # 收集干扰项（排除正确答案本身，且去重）
    distractors = []
    for w in history_manager.get_all_words():
        if w["word"].lower() == word.lower():
            continue
        m = w.get("meaning_zh") or w.get("meaning", "")
        if m and m != correct_meaning and m not in distractors:
            distractors.append(m)

    # 历史不足时用预设基础词补足
    if len(distractors) < 3:
        for m in FALLBACK_MEANINGS.values():
            if m != correct_meaning and m not in distractors:
                distractors.append(m)
            if len(distractors) >= 3:
                break

    distractors = distractors[:3]

    # 组装 4 个选项并随机分配字母
    options = [correct_meaning] + distractors
    random.shuffle(options)

    opt_map = {}
    correct_letter = "A"
    for i, meaning in enumerate(options):
        opt_map[LETTERS[i]] = meaning
        if meaning == correct_meaning:
            correct_letter = LETTERS[i]

    current_quiz["word"] = word
    current_quiz["correct"] = correct_letter
    current_quiz["options"] = opt_map

    lines = [f"🧠 请选出「{word}」的正确意思："]
    for L in LETTERS:
        lines.append(f"{L}. {opt_map[L]}")
    lines.append("回复 A/B/C/D 作答")
    return "\n".join(lines)


def check_answer(user_input):
    """校验用户答案（A/B/C/D，忽略大小写），返回判断结果文本。

    回答正确时调用 history_manager.mark_reviewed 推进该单词的复习进度。
    """
    if not current_quiz.get("word"):
        return "当前没有进行中的测验，先查一个单词试试～"

    ans = (user_input or "").strip().upper()
    if ans not in ("A", "B", "C", "D"):
        return "请回复 A/B/C/D 中的一个字母。"

    correct = current_quiz["correct"]
    word = current_quiz["word"]
    correct_meaning = current_quiz["options"][correct]

    if ans == correct:
        history_manager.mark_reviewed(word)
        return (f"✅ 回答正确！「{word}」的意思是：{correct_meaning}\n"
                f"已推进一次复习进度（当前第 {history_manager.get_word(word)['next_review_index']} / 5 次）。")
    else:
        return (f"❌ 回答错误。正确答案：{correct}. {correct_meaning}\n"
                f"「{word}」的意思：{correct_meaning}")
