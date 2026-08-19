"""系统判题错误题目沉淀（AI 复核判定「参考答案/判题逻辑有误」）

用途：错题复核（judge）或申诉（appeal）发现系统参考答案本身算错、
或本地判题把正确的作答判错时，把题目单独落库，供日后统一修复判题代码 / 题库，
而不是依赖用户逐个报障（045 迁移建表）。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from ..database import Base


class JudgeReviewIssue(Base):
    """AI 复核判定「系统判题/参考答案有误」的题目（待统一修复）"""
    __tablename__ = "judge_review_issues"
    __table_args__ = {"comment": "系统判题错误题目沉淀：参考答案有误/本地判分逻辑错误，待统一修复判题代码"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="触发用户")
    question_id = Column(Integer, nullable=True, index=True, comment="题目 id（题库题）")
    question = Column(Text, nullable=False, comment="题干")
    stored_answer = Column(Text, nullable=True, comment="原存储参考答案")
    correct_answer = Column(Text, nullable=True, comment="AI 修正后的正确值")
    user_answer = Column(Text, nullable=True, comment="孩子作答（触发复核的）")
    subject = Column(String(20), default="", comment="学科")
    reason = Column(String(200), default="", comment="判定原因（stored_wrong/判分逻辑等）")
    source = Column(String(20), default="judge", comment="来源：judge=错题复核 / appeal=申诉")
    status = Column(String(20), default="open", comment="处理状态：open=待修复 / fixed=已修复")
    created_at = Column(DateTime, default=datetime.now, comment="发现时间")


__all__ = ["JudgeReviewIssue"]
