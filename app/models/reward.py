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
    reason = Column(String(200), nullable=True)  # 发券理由（成长奖励记录）
    required_days = Column(Integer, default=0)  # 需全勤天数才可得 1 张；0=即时券
    progress_days = Column(Integer, default=0)  # 已累计全勤天数
    progress_date = Column(String(10), nullable=True)  # 最近累计日期（同日不重复）
    granted_count = Column(Integer, default=0)  # 已获得张数
    redeemed_count = Column(Integer, default=0)  # 已核销张数
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
    redeem_reason = Column(String(200), nullable=True)  # 兑现理由（成长奖励记录）
    # 许愿类型：task_count=完成任务数(旧), optional_streak=连续n天每天完成m个可选任务(新)
    wish_type = Column(String(20), default="task_count")
    daily_target = Column(Integer, default=0)  # 每天需完成的可选任务数（仅 optional_streak 类型）
    last_progress_date = Column(Date, nullable=True)  # 上次进度递增日期（用于连续天数判断）
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
