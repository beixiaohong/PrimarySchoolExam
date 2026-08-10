"""番茄专注钟模型（对应迁移 018 建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class FocusSession(Base):
    """一次完成的专注时段"""
    __tablename__ = "focus_sessions"
    __table_args__ = {"comment": "番茄专注钟：一次完成的专注时段记录"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    minutes = Column(Integer, nullable=False, comment="专注分钟数")
    created_at = Column(DateTime, default=datetime.now, comment="完成时间")
