"""004 新增 AI 用量表、成长周报表、心情打卡表

背景：学习动力改进一期——AI 错题讲解/AI 成长周报/心情打卡功能的数据基础。
ai_usage_log：AI 调用用量与失败日志（成本监控）
weekly_reports：家长成长周报（每周一条，幂等生成）
mood_checkins：心情打卡（每天一次，唯一约束 user+date）
"""
import logging
from datetime import datetime

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Date, DateTime,
    Text, Boolean, UniqueConstraint,
)

logger = logging.getLogger("migrations")


def upgrade(db):
    meta = MetaData()
    Table(
        "ai_usage_log",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("provider", String(30), nullable=False),
        Column("feature", String(30), nullable=False),
        Column("model", String(50), nullable=True),
        Column("prompt_tokens", Integer, nullable=True),
        Column("completion_tokens", Integer, nullable=True),
        Column("ok", Boolean, default=True),
        Column("error", Text, nullable=True),
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=db.get_bind(), checkfirst=True)

    Table(
        "weekly_reports",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("week_start", Date, nullable=False),
        Column("content_json", Text, nullable=True),
        Column("status", String(20), default="pending"),
        Column("created_at", DateTime, default=datetime.now),
        UniqueConstraint("user_id", "week_start", name="uq_user_week"),
    ).create(bind=db.get_bind(), checkfirst=True)

    Table(
        "mood_checkins",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("check_date", Date, nullable=False),
        Column("mood", String(20), nullable=False),
        Column("note", String(100), nullable=True),
        Column("created_at", DateTime, default=datetime.now),
        UniqueConstraint("user_id", "check_date", name="uq_user_mood_date"),
    ).create(bind=db.get_bind(), checkfirst=True)

    logger.info("ai_usage_log / weekly_reports / mood_checkins 表已创建")
