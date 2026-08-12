"""补签卡模型：完成每日全部可选任务获得，可将中断日补签为全勤"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String

from ..database import Base


class MakeupCard(Base):
    """补签卡余额（按用户汇总，使用一条记录记余额）"""
    __tablename__ = "makeup_cards"
    __table_args__ = {"comment": "补签卡余额：每用户一条，连续全勤发放，用于断签补签"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, unique=True, index=True, comment="用户名")
    balance = Column(Integer, default=0, comment="当前可用补签卡数量")
    total_earned = Column(Integer, default=0, comment="累计获得数量")
    total_used = Column(Integer, default=0, comment="累计使用数量")
    last_grant_date = Column(Date, nullable=True, comment="最近一次发放日期（每日去重用，防刷）")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class MakeupUsageLog(Base):
    """补签卡使用记录

    status 状态机：
    - pending   ：已扣卡、待家长确认（孩子发起的补签卡完成任意任务走此态）
    - confirmed ：家长已确认，效果生效（补签某天默认即生效，故为 confirmed）
    - rejected  ：家长拒绝，补签卡已退回
    task_id 仅当孩子用补签卡完成某条每日任务时关联，补签某天时为 NULL。
    """
    __tablename__ = "makeup_usage_log"
    __table_args__ = {"comment": "补签卡使用记录：每次扣卡/确认的状态流转"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    target_date = Column(Date, nullable=False, comment="补签的目标日期（补签某天用）")
    used_at = Column(DateTime, default=datetime.now, comment="使用时间")
    status = Column(String(20), nullable=False, default="confirmed",
                    comment="pending 待确认 / confirmed 已生效 / rejected 已退回")
    task_id = Column(Integer, nullable=True, index=True, comment="关联的每日任务 id（补签卡完成任意任务时填写）")
