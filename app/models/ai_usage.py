"""AI 用量与周报模型（对应迁移 004 建表）"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, Date, DateTime, Integer, String,
                        Text, UniqueConstraint)

from ..database import Base


class AIUsageLog(Base):
    """AI 调用用量日志（成本监控）"""
    __tablename__ = "ai_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    provider = Column(String(30), nullable=False)
    feature = Column(String(30), nullable=False)
    model = Column(String(50), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    ok = Column(Boolean, default=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class WeeklyReport(Base):
    """家长成长周报（每周一条，幂等）"""
    __tablename__ = "weekly_reports"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_user_week"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    content_json = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    parent_note = Column(String(200), default="")  # 家长寄语（006 迁移）
    created_at = Column(DateTime, default=datetime.now)


class AiQa(Base):
    """AI 问答缓存（十万个为什么 + 错题讲解，全局共享，相同问题不再请求 AI）"""
    __tablename__ = "ai_qa"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    provider = Column(String(30), nullable=False, default="")
    model = Column(String(50), nullable=False, default="")
    q_type = Column(String(10), nullable=False, default="qa")  # qa=提问 / explain=讲解
    ref_id = Column(Integer, nullable=True)  # explain 时为题目 id
    degraded = Column(Integer, nullable=False, default=0)  # 降级模板不参与缓存命中
    created_at = Column(DateTime, default=datetime.now)
