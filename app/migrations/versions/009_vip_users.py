"""009 新增 VIP 名单表 vip_users（按 user_id 隔离付费链）

背景：付费链（DeepSeek）只对 VIP 用户开放。此前名单硬编码在
app/services/ai.py 的 VIP_USERS 集合（改名单要改代码），现迁移到
数据库表，按 user_id 精确匹配，增删 VIP 只需操作本表（无需重启）。

vip_users：user_id 主键 + note 备注 + created_at
种子数据：保留原有硬编码名单（诗文、橙子）。
"""
import logging
from datetime import datetime

from sqlalchemy import MetaData, Table, Column, String, DateTime
from sqlalchemy import text

logger = logging.getLogger("migrations")

SEED_VIP = ["诗文", "橙子"]


def upgrade(db):
    meta = MetaData()
    # 新建 VIP 名单表（按 user_id 精确匹配，替代硬编码名单）
    Table(
        "vip_users",
        meta,
        Column("user_id", String(50), primary_key=True,
               comment="登录用户名，与业务表 user_id 一致"),
        Column("note", String(100), nullable=False, default="",
               comment="备注（如：家长开通）"),
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=db.get_bind(), checkfirst=True)
    # 种子：迁移原硬编码名单（幂等，已存在则跳过）
    for uid in SEED_VIP:
        db.execute(
            text("INSERT OR IGNORE INTO vip_users (user_id, note) VALUES (:u, :n)"),
            {"u": uid, "n": "迁移自原硬编码名单"},
        )
    db.commit()
    logger.info("vip_users 表已创建，种子名单：%s", SEED_VIP)
