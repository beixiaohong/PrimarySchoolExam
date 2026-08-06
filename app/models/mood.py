"""心情打卡模型（对应迁移 004 建表）"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint

from ..database import Base


class MoodCheckin(Base):
    """学习心情打卡（每天一次）"""
    __tablename__ = "mood_checkins"
    __table_args__ = (UniqueConstraint("user_id", "check_date", name="uq_user_mood_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    check_date = Column(Date, nullable=False)
    mood = Column(String(20), nullable=False)  # great/happy/ok/blue/sad
    note = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
