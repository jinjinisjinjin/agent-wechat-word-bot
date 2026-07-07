"""
scheduler.py — 定时任务模块

使用 schedule 库设置两个定时任务：
1. 每天 08:00  daily_job()  —— 今日复习推送（含一道测验题）
2. 每周一 08:30 weekly_job() —— 学习周报推送

推送通过 set_sender() 注入的发送函数完成（由 main.py 注入 cc-weixin 发送接口）。
"""
import schedule
import time
import threading

import history_manager
import quiz_manager
import weekly_report

# 发送函数（由 main 注入），默认 None（仅打印到控制台）
_sender = None


def set_sender(func):
    """注入发送函数：func(text: str) -> None。main.py 在启动时调用。"""
    global _sender
    _sender = func


def _push(text):
    """将文本推送给用户：若已注入发送器则用发送器，否则打印到控制台。"""
    if _sender:
        _sender(text)
    else:
        print("[scheduler] （未配置发送器）推送内容：\n" + text)


def daily_job():
    """每日复习推送任务。

    - 获取今天到期单词；有则格式化复习列表，无则提示“今天没有复习任务”。
    - 以第一个到期单词（无则随机历史词）生成一道测验题。
    - 将复习消息与测验消息合并为一条推送。
    """
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    due = history_manager.get_due_words(today)

    if due:
        lines = [f"📚 今日复习（{len(due)} 个词）"]
        for i, w in enumerate(due, 1):
            lines.append(f"{i}. {w['word']} {w.get('phonetic', '')} {w.get('meaning', '')}")
        review_text = "\n".join(lines)
    else:
        review_text = "今天没有复习任务 🎉"

    # 选取测验单词
    if due:
        quiz_word = due[0]["word"]
    else:
        all_words = history_manager.get_all_words()
        quiz_word = all_words[0]["word"] if all_words else None

    quiz_text = quiz_manager.generate_quiz(quiz_word) if quiz_word else ""

    combined = review_text
    if quiz_text:
        combined += "\n\n" + quiz_text
    _push(combined)


def weekly_job():
    """每周周报推送任务。"""
    report = weekly_report.generate_weekly_report()
    _push(report)


def run_scheduler():
    """注册定时任务并在后台守护线程中启动调度循环。"""
    schedule.every().day.at("08:00").do(daily_job)
    schedule.every().monday.at("08:30").do(weekly_job)

    def _loop():
        while True:
            schedule.run_pending()
            time.sleep(1)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
