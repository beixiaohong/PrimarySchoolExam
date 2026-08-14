"""031_im_tables：IM 即时通讯模块建表

创建 7 张 IM 表：
- db_im_chats / db_im_messages / db_im_friendships
- db_im_group_members / db_im_red_packets / db_im_red_packet_claims
- db_im_read_receipts

并幂等为 users 表补充 IM 依赖的 4 个字段（不修改任何已有文件）：
- avatar   VARCHAR(255)   头像 URL
- points   INTEGER         积分（红包/好友消耗）
- is_online TINYINT(1)     在线状态
- last_seen DATETIME       最后活跃时间

建表遵循项目规范：Base.metadata.create_all(bind=engine, tables=[...])。
users 加列用信息_schema 幂等判断，列已存在则跳过。
"""
import logging

from sqlalchemy import text

from app.database import Base, engine
from app.models.im import (
    Chat, Message, Friendship, GroupMember, RedPacket, RedPacketClaim, ReadReceipt,
)

logger = logging.getLogger("migrations")

# users 表需补充的 IM 相关列（列名, MySQL 类型）
USER_IM_COLUMNS = [
    ("avatar", "VARCHAR(255) NULL"),
    ("points", "INTEGER NULL DEFAULT 0"),
    ("is_online", "TINYINT(1) NULL DEFAULT 0"),
    ("last_seen", "DATETIME NULL"),
]


def upgrade(db):
    # 1) 创建 7 张 IM 表（已存在则跳过）
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Chat.__table__, Message.__table__, Friendship.__table__,
            GroupMember.__table__, RedPacket.__table__, RedPacketClaim.__table__,
            ReadReceipt.__table__,
        ],
    )
    logger.info("031_im_tables: IM 表已就绪")

    # 2) 幂等为 users 表补充 IM 依赖字段
    for col_name, col_type in USER_IM_COLUMNS:
        result = db.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
            f"AND COLUMN_NAME = '{col_name}'"
        ))
        if result.scalar() == 0:
            db.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
            logger.info(f"031_im_tables: users 已添加列 {col_name}")
        else:
            logger.info(f"031_im_tables: users 列 {col_name} 已存在，跳过")

    # 回填：已存在用户 points/is_online 可能为 NULL（ALTER 不回填），置默认值避免比较报错
    db.execute(text("UPDATE users SET points = 0 WHERE points IS NULL"))
    db.execute(text("UPDATE users SET is_online = 0 WHERE is_online IS NULL"))

    db.commit()
    logger.info("031_im_tables: 迁移完成")


def downgrade(db):
    # 仅删除本次新增的 users 列（IM 表保留由各自负责人处理）
    for col_name, _ in USER_IM_COLUMNS:
        result = db.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
            f"AND COLUMN_NAME = '{col_name}'"
        ))
        if result.scalar() > 0:
            db.execute(text(f"ALTER TABLE users DROP COLUMN {col_name}"))
            logger.info(f"031_im_tables: users 已回滚列 {col_name}")
    db.commit()
