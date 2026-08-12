"""背单词模块 Pydantic schemas"""
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class VocabWordOut(BaseModel):
    """今日单词输出"""
    word_id: int  # 单词 ID
    word: str  # 单词拼写
    phonetic: str  # 音标
    pos: str  # 词性
    meaning: str  # 中文释义
    unit: str  # 所属单元
    difficulty: int  # 难度档
    is_new: bool  # True=新词, False=复习词
    review_stage: int = 0  # 当前复习阶段


class LearnRequest(BaseModel):
    """学习新词请求"""
    user_id: str  # 用户标识
    word_ids: List[int]  # 标记为"已学会"的单词ID列表


class ReviewRequest(BaseModel):
    """复习请求"""
    user_id: str  # 用户标识
    results: List[dict]  # [{word_id: int, correct: bool}, ...]


class VocabStatsOut(BaseModel):
    """用户词汇学习统计"""
    total_words: int  # 词库总词数（当前年级）
    learned_count: int  # 已学习（含学习中）
    mastered_count: int  # 已掌握
    learning_count: int  # 学习中
    new_today: int  # 今日新学
    review_today: int  # 今日复习
    due_today: int  # 今日待复习
    streak_days: int  # 连续学习天数
    total_learned_all_time: int  # 累计学习总数


class TodayTaskOut(BaseModel):
    """今日任务概览"""
    new_words: List[VocabWordOut]  # 今日新词（最多10个）
    review_words: List[VocabWordOut]  # 待复习词
    stats: dict  # 简要统计


class VocabProgressOut(BaseModel):
    """单词进度详情"""
    word_id: int  # 单词 ID
    word: str  # 单词拼写
    meaning: str  # 中文释义
    status: str  # 学习状态（学习中/已掌握等）
    review_stage: int  # 当前复习阶段
    next_review_date: Optional[date]  # 下次复习日期（None=未排期）
    correct_count: int  # 累计答对次数
    wrong_count: int  # 累计答错次数
    total_reviews: int  # 总复习次数
