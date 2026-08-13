"""奖励闭环与目标模型（对应迁移 005 建表）"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String

from ..database import Base


class RewardCoupon(Base):
    """家长创建的奖励兑换券"""
    __tablename__ = "reward_coupons"
    __table_args__ = {"comment": "奖励兑换券：家长创建，支持即时券与全勤成长券"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    title = Column(String(100), nullable=False, comment="券名称")
    kind = Column(String(30), default="custom", comment="类型：cartoon/snack/sticker/toy/outing/custom")
    max_per_month = Column(Integer, default=2, comment="每月兑换上限")
    used_count = Column(Integer, default=0, comment="已兑换次数")
    reason = Column(String(200), nullable=True, comment="发券理由（成长奖励记录）")
    required_days = Column(Integer, default=0, comment="需全勤天数才可得 1 张；0=即时券")
    required_within_days = Column(Integer, default=0, comment="必须在多少天内达成全勤天数；0=不限期（旧行为）")
    cycle_start_date = Column(String(10), nullable=True, comment="当前计周期起始日（YYYY-MM-DD），用于 within_days 窗口；到期未达标则重置该周期")
    progress_days = Column(Integer, default=0, comment="已累计全勤天数")
    progress_date = Column(String(10), nullable=True, comment="最近累计日期（同日不重复）")
    granted_count = Column(Integer, default=0, comment="已获得张数")
    redeemed_count = Column(Integer, default=0, comment="已核销张数")
    status = Column(String(20), default="active", comment="active/archived")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class WishItem(Base):
    """孩子心愿单（同时仅 1 个进行中）"""
    __tablename__ = "wish_items"
    __table_args__ = {"comment": "孩子心愿单：同时仅 1 个进行中，达成后家长兑现"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    title = Column(String(100), nullable=False, comment="心愿名称")
    progress = Column(Integer, default=0, comment="当前进度")
    target = Column(Integer, default=10, comment="目标值")
    status = Column(String(20), default="active", comment="active/pending/redeemed/archived")
    redeem_reason = Column(String(200), nullable=True, comment="兑现理由（成长奖励记录）")
    # 许愿类型：task_count=完成任务数(旧), optional_streak=连续n天每天完成m个可选任务(新)
    wish_type = Column(String(20), default="task_count", comment="许愿类型：task_count/optional_streak")
    daily_target = Column(Integer, default=0, comment="每天需完成的可选任务数（仅 optional_streak 类型）")
    last_progress_date = Column(Date, nullable=True, comment="上次进度递增日期（用于连续天数判断）")
    deadline = Column(Date, nullable=True, comment="截止日期（超过后未完成自动过期）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class GoalItem(Base):
    """学期目标（分数/灭错/背诵）"""
    __tablename__ = "goal_items"
    __table_args__ = {"comment": "学期目标：分数/灭错/背诵，家长或学生设定并跟踪"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    kind = Column(String(20), nullable=False, comment="目标类型：score/wrong/recite")
    title = Column(String(100), nullable=False, comment="目标名称")
    subject = Column(String(20), nullable=True, comment="学科（可选）")
    target = Column(Integer, default=90, comment="目标值")
    current = Column(Integer, default=0, comment="当前值")
    deadline = Column(Date, nullable=True, comment="截止日期")
    status = Column(String(20), default="active", comment="active/done/archived")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
