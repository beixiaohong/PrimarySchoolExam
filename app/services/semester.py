"""学期与学段判断工具

学期规则（与国内校历一致）：9 月-次年 1 月为上学期，2-8 月为下学期。
7-8 月暑假按下学期归属，配合 include_next 预习开关使用。
"""
from datetime import date
from typing import Optional


def current_semester(today: Optional[date] = None) -> str:
    """返回当前学期：上/下"""
    today = today or date.today()
    # 9-12 月、1 月为上学期；2-8 月为下学期
    return "上" if today.month >= 9 or today.month == 1 else "下"


def next_semester(today: Optional[date] = None) -> str:
    """返回下学期（与当前学期相反）"""
    return "下" if current_semester(today) == "上" else "上"


def stage_label(grade: int) -> str:
    """学段名称：1-6 小学，7-9 初中，10-12 高中"""
    if grade <= 6:
        return "小学"
    if grade <= 9:
        return "初中"
    return "高中"
