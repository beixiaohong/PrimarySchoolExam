"""奖励闭环与目标模型（对应迁移 005 建表）"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String

from ..database import Base


class RewardCoupon(Base):
    """家长创建的奖励兑换券"""
    __tablename__ = "reward_coupons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    kind = Column(String(30), default="custom")  # cartoon/snack/sticker/toy/outing/custom
    max_per_month = Column(Integer, default=2)
    used_count = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active/archived
    created_at = Column(DateTime, default=datetime.now)


class WishItem(Base):
    """孩子心愿单（同时仅 1 个进行中）"""
    __tablename__ = "wish_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    progress = Column(Integer, default=0)
    target = Column(Integer, default=10)
    status = Column(String(20), default="active")  # active/pending/redeemed/archived
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class GoalItem(Base):
    """学期目标（分数/灭错/背诵）"""
    __tablename__ = "goal_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # score/wrong/recite
    title = Column(String(100), nullable=False)
    subject = Column(String(20), nullable=True)
    target = Column(Integer, default=90)
    current = Column(Integer, default=0)
    deadline = Column(Date, nullable=True)
    status = Column(String(20), default="active")  # active/done/archived
    created_at = Column(DateTime, default=datetime.now)
