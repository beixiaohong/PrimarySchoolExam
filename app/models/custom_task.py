"""自定义任务模型：孩子创建，家长确认"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class CustomTask(Base):
    """孩子自定义每日任务"""
    __tablename__ = "custom_tasks"
    __table_args__ = {"comment": "自定义任务：孩子创建，家长确认后生效"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    title = Column(String(100), nullable=False, comment="任务标题")
    subject = Column(String(20), default="其他", comment="学科分类")
    status = Column(String(20), default="pending", comment="pending/confirmed/rejected")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    confirmed_at = Column(DateTime, nullable=True, comment="家长确认时间")
