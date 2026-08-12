"""008 新增家长任务设置表 parent_task_settings

背景：每日任务题目数量由家长在家长面板配置（如"数学练习做 2 套"、
"英语学 10 个新词"）。设置按用户存一行 JSON（只存覆盖默认值的项），
每日任务生成/更换时优先使用家长设置的目标数量。

parent_task_settings：user_id 主键 + settings_json（{"math_exam": 2, ...}）
"""
import logging
from datetime import datetime

from sqlalchemy import MetaData, Table, Column, Integer, String, DateTime, Text

logger = logging.getLogger("migrations")


def upgrade(db):
    meta = MetaData()
    # 新建家长任务设置表（每用户一行 JSON，覆盖默认每日任务量）
    Table(
        "parent_task_settings",
        meta,
        Column("user_id", String(50), primary_key=True,
               comment="用户名（与每日任务表一致）"),
        Column("settings_json", Text, nullable=False, default="{}",
               comment='JSON：{"task_code": target}，只存与默认值不同的项'),
        Column("updated_at", DateTime, default=datetime.now, onupdate=datetime.now),
    ).create(bind=db.get_bind(), checkfirst=True)
    logger.info("parent_task_settings 表已创建")
