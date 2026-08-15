"""032_announcements：系统公告表

仅建 admin_announcements 一张表（建表无 DEFAULT 约束，跨 dialect 安全）。
"""
import logging

from app.database import Base, engine
from app.models.announcement import Announcement

logger = logging.getLogger("migrations")


def upgrade(db):
    """建表迁移：创建 admin_announcements 系统公告表。"""
    Base.metadata.create_all(bind=engine, tables=[Announcement.__table__])
    logger.info("032_announcements: admin_announcements 表已就绪")


def downgrade(db):
    """回滚迁移：删除 admin_announcements 系统公告表。"""
    Announcement.__table__.drop(bind=engine, checkfirst=True)
