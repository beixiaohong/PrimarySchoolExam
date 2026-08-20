"""048 - 网课表（online_courses：系统配置 + 家长自定义）

背景（需求：网课模块，默认显示系统配置的网课，家长也可单独配置）：
- source=system：后台配置，全用户可见（按学科/年级过滤）
- source=parent：家长为孩子单独配置（parent_uid=创建者账号）
- 视频 URL 形式（b站/腾讯视频/直链 mp4），不做文件上传

幂等：checkfirst 建表，MySQL-only。
"""
import logging
from datetime import datetime

from sqlalchemy import MetaData, Table, Column, Integer, String, Boolean, DateTime, Text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    meta = MetaData()
    Table(
        "online_courses",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("subject", String(20), nullable=False, default="", index=True),
        Column("grade", Integer, nullable=False, default=0, index=True),
        Column("title", String(100), nullable=False),
        Column("description", Text, nullable=False, default=""),
        Column("cover_url", String(500), nullable=False, default=""),
        Column("video_url", String(500), nullable=False, default=""),
        Column("duration_min", Integer, nullable=False, default=0),
        Column("source", String(20), nullable=False, default="system"),
        Column("parent_uid", String(50), nullable=True, index=True),
        Column("enabled", Boolean, nullable=False, default=True),
        Column("sort_order", Integer, nullable=False, default=0),
        Column("created_at", DateTime, default=datetime.now),
    ).create(bind=bind, checkfirst=True)
    logger.info("online_courses 表已创建（网课：系统配置 + 家长自定义）")
