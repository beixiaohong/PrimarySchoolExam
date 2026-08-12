"""018 番茄专注钟：focus_sessions 专注记录表

孩子用番茄钟专注学习，每完成一次专注（10/15/25 分钟）记录一条，
并奖励金币 +2（与宠物系统联动）。按天聚合统计展示。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    with bind.begin() as conn:
        # 新建番茄专注记录表（每完成一次专注一条，联动金币）
        conn.execute(text(
            """CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(64) NOT NULL,
                minutes INTEGER NOT NULL,
                created_at DATETIME
            )"""
        ))
    logger.info("018: focus_sessions 已建表")
