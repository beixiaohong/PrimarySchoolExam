"""011 家长功能独立：家长密码 + 试卷最少题数 + 家长消息 + 奖励理由

背景：家长管理入口（设置-家长管理）此前无任何验证，孩子可随意进入。
本次：
- parent_passwords：家长密码（按孩子 user_id 存一份），含密保问题/答案（忘记密码时重置）
- exam_min_counts：每科试卷最少题数（数学/语文/英语分别设置，生成试卷时强制下限）
- parent_messages：家长发给孩子的留言（read_at 标记已读）
- reward_coupons 增加 reason（发券理由）、wish_items 增加 redeem_reason（兑现理由）
  → 形成孩子的成长奖励记录
"""
import logging
from datetime import datetime

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, DateTime, text,
)
from sqlalchemy import inspect as sa_inspect

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    meta = MetaData()
    Table(
        "parent_passwords",
        meta,
        Column("user_id", String(50), primary_key=True),
        Column("password_hash", String(200), nullable=False),
        Column("hint_question", String(100), nullable=False),
        Column("hint_answer_hash", String(200), nullable=False),
        Column("created_at", DateTime, default=datetime.now),
        Column("updated_at", DateTime, default=datetime.now, onupdate=datetime.now),
    ).create(bind=bind, checkfirst=True)

    Table(
        "exam_min_counts",
        meta,
        Column("user_id", String(50), primary_key=True),
        Column("math_min", Integer, default=5),
        Column("chi_min", Integer, default=5),
        Column("eng_min", Integer, default=5),
        Column("updated_at", DateTime, default=datetime.now, onupdate=datetime.now),
    ).create(bind=bind, checkfirst=True)

    Table(
        "parent_messages",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", String(50), nullable=False, index=True),
        Column("content", String(300), nullable=False),
        Column("read_at", DateTime, nullable=True),
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=bind, checkfirst=True)

    # 已有表加列（幂等：列已存在则跳过）
    insp = sa_inspect(bind)
    if "reward_coupons" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("reward_coupons")}
        if "reason" not in cols:
            db.execute(text("ALTER TABLE reward_coupons ADD COLUMN reason VARCHAR(200)"))
            logger.info("reward_coupons.reason 已添加")
    if "wish_items" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("wish_items")}
        if "redeem_reason" not in cols:
            db.execute(text("ALTER TABLE wish_items ADD COLUMN redeem_reason VARCHAR(200)"))
            logger.info("wish_items.redeem_reason 已添加")

    logger.info("parent_passwords / exam_min_counts / parent_messages 表已创建，券/心愿加理由列")
