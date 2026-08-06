"""005 新增奖励兑换券表、心愿单表、学期目标表

背景：学习动力改进一期——奖励闭环（兑换券+心愿单）与目标倒计时功能。
reward_coupons：家长创建的奖励兑换券（6 类模板 + 自定义）
wish_items：孩子心愿单（同时仅 1 个进行中）
goal_items：学期目标（分数/灭错/背诵三类，倒计时）
"""
import logging
from datetime import datetime

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Date, DateTime,
    Boolean, UniqueConstraint,
)

logger = logging.getLogger("migrations")


def upgrade(db):
    meta = MetaData()
    Table(
        "reward_coupons",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("title", String(100), nullable=False),
        Column("kind", String(30), default="custom"),
        Column("max_per_month", Integer, default=2),
        Column("used_count", Integer, default=0),
        Column("status", String(20), default="active"),
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=db.get_bind(), checkfirst=True)

    Table(
        "wish_items",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("title", String(100), nullable=False),
        Column("progress", Integer, default=0),
        Column("target", Integer, default=10),
        Column("status", String(20), default="active"),  # active/pending/redeemed/archived
        Column("created_at", DateTime, default=datetime.now),
        Column("updated_at", DateTime, default=datetime.now, onupdate=datetime.now),
    ).create(bind=db.get_bind(), checkfirst=True)

    Table(
        "goal_items",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("kind", String(20), nullable=False),  # score/wrong/recite
        Column("title", String(100), nullable=False),
        Column("subject", String(20), nullable=True),
        Column("target", Integer, default=90),
        Column("current", Integer, default=0),
        Column("deadline", Date, nullable=True),
        Column("status", String(20), default="active"),  # active/done/archived
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=db.get_bind(), checkfirst=True)

    logger.info("reward_coupons / wish_items / goal_items 表已创建")
