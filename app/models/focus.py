"""番茄专注钟模型（对应迁移 018 建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class FocusSession(Base):
    """一次完成的专注时段"""
    __tablename__ = "focus_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    minutes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
