"""心情打卡模型（对应迁移 004 建表）"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint

from ..database import Base


class MoodCheckin(Base):
    """学习心情打卡（每天一次）"""
    __tablename__ = "mood_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "check_date", name="uq_user_mood_date"),
        {"comment": "学习心情打卡：每用户每天一次，供家长关注孩子情绪"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    check_date = Column(Date, nullable=False, comment="打卡日期")
    mood = Column(String(20), nullable=False, comment="心情：great/happy/ok/blue/sad")
    note = Column(String(100), nullable=True, comment="心情备注")
    created_at = Column(DateTime, default=datetime.now, comment="打卡时间")
