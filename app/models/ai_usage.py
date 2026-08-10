"""AI 用量与周报模型（对应迁移 004 建表）"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, Date, DateTime, Integer, String,
                        Text, UniqueConstraint)

from ..database import Base


class AIUsageLog(Base):
    """AI 调用用量日志（成本监控）"""
    __tablename__ = "ai_usage_log"
    __table_args__ = {"comment": "AI 调用用量日志：记录每次请求的模型/token/成败，用于成本监控"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    provider = Column(String(30), nullable=False, comment="AI 供应商")
    feature = Column(String(30), nullable=False, comment="功能场景（出题/讲解/周报等）")
    model = Column(String(50), nullable=True, comment="模型名称")
    prompt_tokens = Column(Integer, nullable=True, comment="输入 token 数")
    completion_tokens = Column(Integer, nullable=True, comment="输出 token 数")
    ok = Column(Boolean, default=True, comment="调用是否成功")
    error = Column(Text, nullable=True, comment="失败错误信息")
    created_at = Column(DateTime, default=datetime.now, comment="调用时间")


class WeeklyReport(Base):
    """家长成长周报（每周一条，幂等）"""
    __tablename__ = "weekly_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_user_week"),
        {"comment": "家长成长周报：每用户每周一条（幂等），含家长寄语"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    week_start = Column(Date, nullable=False, comment="周报所在周的周一日期")
    content_json = Column(Text, nullable=True, comment="周报内容 JSON")
    status = Column(String(20), default="pending", comment="生成状态：pending/done/failed")
    parent_note = Column(String(200), default="", comment="家长寄语（006 迁移）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class AiQa(Base):
    """AI 问答缓存（十万个为什么 + 错题讲解，全局共享，相同问题不再请求 AI）

    session_id（015 迁移）：多轮对话会话标识；为空表示单轮提问（命中全局缓存）
    """
    __tablename__ = "ai_qa"
    __table_args__ = {"comment": "AI 问答缓存：十万个为什么+错题讲解，全局共享，相同问题不再请求 AI"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    question = Column(Text, nullable=False, comment="问题内容")
    answer = Column(Text, nullable=False, comment="AI 回答内容")
    provider = Column(String(30), nullable=False, default="", comment="AI 供应商")
    model = Column(String(50), nullable=False, default="", comment="模型名称")
    q_type = Column(String(10), nullable=False, default="qa", comment="类型：qa=提问 / explain=讲解")
    ref_id = Column(Integer, nullable=True, comment="explain 时为题目 id")
    degraded = Column(Integer, nullable=False, default=0, comment="降级模板标记，不参与缓存命中")
    session_id = Column(String(40), nullable=True, index=True, comment="多轮对话会话（015 迁移，空=单轮）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
