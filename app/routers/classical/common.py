"""古诗文背诵模块 API 路由（shared：schemas / helpers / constants）

本文件只承载跨子模块共享的定义，不含任何路由。router 定义在包 __init__.py。
"""
import json
import random
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.classical import ClassicalText, ClassicalProgress, ClassicalDailyLog
from app.models.study_error import StudyError

# 拼音（古诗文逐行展示用）：缺依赖时优雅降级，仅隐藏拼音，不影响主流程
try:
    from pypinyin import pinyin as _py_pinyin, Style as _PyStyle
    _HAS_PINYIN = True
except Exception:
    _HAS_PINYIN = False
    _py_pinyin = None
    _PyStyle = None

# 艾宾浩斯间隔（天）
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30]
# 每天新学篇数
NEW_TEXTS_PER_DAY = 5


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════

class ClassicalTextCreate(BaseModel):
    """古诗文录入请求体：标题（必填）、作者、朝代、类型、年级、全文内容与标签。"""
    title: str
    author: str = ""
    dynasty: str = ""
    text_type: str = "poem"  # poem / prose
    grade: int = 3
    content: str  # 全文，行用\n分隔
    tags: str = ""


class ClassicalTextOut(BaseModel):
    """古诗文输出模型：篇目元数据 + 逐行内容、逐行拼音、标签等展示字段。"""
    id: int
    title: str
    author: str
    dynasty: str
    text_type: str
    grade: int
    content: str
    lines: list
    pinyin: list = []   # 逐行拼音（带声调），前端逐行展示用
    tags: str


class QuizQuestionOut(BaseModel):
    """古诗文填空题输出模型：篇目信息、题干、答案与上下文提示。"""
    text_id: int
    title: str
    author: str
    question: str
    answer: str
    context: str  # 上下文提示


class LearnRequest(BaseModel):
    """标记篇目已学习请求体：用户 ID 与待标记的篇目 ID 列表。"""
    user_id: str
    text_ids: List[int]


class ReviewRequest(BaseModel):
    """提交背诵复习结果请求体：用户 ID 与每篇正确与否的结果列表。"""
    user_id: str
    results: List[dict]  # [{text_id, correct}]
    wrong_items: List[dict] = []  # AI 复审：[{text_id, question, user_answer, answer, subject}]


class DictateRequest(BaseModel):
    """古诗文默写提交请求体：用户 ID、模式及（兼容/新）正确篇目 ID 列表。"""
    user_id: str
    mode: str = "new"  # new=新学 / review=复习
    text_ids: List[int] = []      # 向后兼容：旧前端传「全部正确」的篇目
    passed_ids: List[int] = []    # 新：默写正确的篇目（前端判分后仅传正确的，错的已剔除）
    wrong_items: List[dict] = []  # AI 复审：[{text_id, question, user_answer, answer, subject}]


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _parse_lines(content: str) -> list:
    """将全文按换行分割成行列表，过滤空行"""
    return [line.strip() for line in content.strip().split("\n") if line.strip()]


def _pinyin_lines(content: str) -> list:
    """返回与正文逐行对应的拼音行（每行空格分隔带声调），无 pypinyin 时返回空列表。"""
    if not _HAS_PINYIN:
        return []
    out = []
    for ln in _parse_lines(content or ""):
        py = _py_pinyin(ln, style=_PyStyle.TONE, heteronym=False)
        out.append(" ".join(seg[0] for seg in py))
    return out


def _calc_next_review(stage: int, from_date: date) -> date:
    """根据复习阶段计算下次复习日期：按艾宾浩斯间隔表取对应天数；已超最高阶段则固定 30 天后复查。"""
    if stage >= len(EBBINGHAUS_INTERVALS):
        return from_date + timedelta(days=30)
    return from_date + timedelta(days=EBBINGHAUS_INTERVALS[stage])


def _get_today_log(db: Session, user_id: str, today: date) -> ClassicalDailyLog:
    """获取或创建用户当日古诗文学习日志：不存在则新建并落库，返回 DailyLog 对象。"""
    log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.learn_date == today
    ).first()
    if not log:
        log = ClassicalDailyLog(user_id=user_id, learn_date=today)
        db.add(log)
        db.commit()
        db.refresh(log)
    return log


def _get_streak(db: Session, user_id: str) -> int:
    """计算用户古诗文连续学习天数：从今天（或最近学习日）向前逐日回溯含学习记录的连续天数。"""
    logs = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.texts_learned > 0
    ).order_by(ClassicalDailyLog.learn_date.desc()).all()
    if not logs:
        return 0
    streak = 0
    check_date = date.today()
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date
    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


_TRAILING_PUNCT = "，。！？；：、,.!?;:"


def _strip_punct(s: str) -> str:
    """去掉行尾标点，避免与题干模板标点重复"""
    return s.rstrip(_TRAILING_PUNCT)


__all__ = [
    "EBBINGHAUS_INTERVALS",
    "NEW_TEXTS_PER_DAY",
    "_HAS_PINYIN",
    "_py_pinyin",
    "_PyStyle",
    "_TRAILING_PUNCT",
    "_parse_lines",
    "_pinyin_lines",
    "_strip_punct",
    "_calc_next_review",
    "_get_today_log",
    "_get_streak",
    "ClassicalTextCreate",
    "ClassicalTextOut",
    "QuizQuestionOut",
    "LearnRequest",
    "ReviewRequest",
    "DictateRequest",
]
