"""
weekly_report.py — 周报生成模块

生成上周（7 天前 ~ 昨天，共 7 天）的学习周报文本。
"""
import history_manager
from datetime import datetime, timedelta


def generate_weekly_report():
    """计算上周日期范围，调用 history_manager 统计，返回报告文本。"""
    today = datetime.now()
    # 上周区间：昨天往前推 6 天（即 7 天前 ~ 昨天，共 7 天）
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    stats = history_manager.get_weekly_stats(start_str, end_str)

    lines = [
        "📅 学习周报",
        f"统计区间：{start_str} ~ {end_str}",
        f"本周新增：{stats['new_words']} 个",
        f"完成复习：{stats['reviews_done']} 次",
    ]
    top = stats.get("top_words", [])
    if top:
        lines.append("热词 Top3：")
        for i, (w, c) in enumerate(top, 1):
            lines.append(f"  {i}. {w}（{c} 次）")
    else:
        lines.append("热词 Top3：暂无")

    return "\n".join(lines)
