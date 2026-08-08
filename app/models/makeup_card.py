"""补签卡模型：完成每日全部可选任务获得，可将中断日补签为全勤"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String

from ..database import Base


class MakeupCard(Base):
    """补签卡余额（按用户汇总，使用一条记录记余额）"""
    __tablename__ = "makeup_cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, unique=True, index=True, comment="用户名")
    balance = Column(Integer, default=0, comment="当前可用补签卡数量")
    total_earned = Column(Integer, default=0, comment="累计获得数量")
    total_used = Column(Integer, default=0, comment="累计使用数量")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MakeupUsageLog(Base):
    """补签卡使用记录"""
    __tablename__ = "makeup_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    target_date = Column(Date, nullable=False, comment="补签的目标日期")
    used_at = Column(DateTime, default=datetime.now)
