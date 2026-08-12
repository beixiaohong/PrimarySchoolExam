"""017 成就徽章：badge_earned 用户获得记录表

徽章规则硬编码在 routers/badges.py（从学习数据派生判断），
本表只记录「何时首次达成」，用于徽章墙展示授予时间与里程碑感。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()
    with bind.begin() as conn:
        # 新建成就徽章获得记录表（记录首次达成时间）
        conn.execute(text(
            """CREATE TABLE IF NOT EXISTS badge_earned (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(64) NOT NULL,
                badge_code VARCHAR(40) NOT NULL,
                earned_at DATETIME,
                UNIQUE (user_id, badge_code)
            )"""
        ))
    logger.info("017: badge_earned 已建表")
