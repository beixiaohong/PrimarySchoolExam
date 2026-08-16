"""042 - 任务有效期与重置：wish_items / goal_items 增加 validity_days 列

用途：记录任务创建时的「有效期天数」(deadline - 创建日)，用于判定「必然完成不了」
时执行「清零重发」——把 deadline 顺延为 今天 + validity_days，重新给一个完整有效期。

MySQL-only（ALTER TABLE ADD COLUMN 为 MySQL 专属）。幂等：用 information_schema
检测列是否存在，已存在则跳过。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def _add_column(db, table, column, ddl):
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}'"
    ))
    if result.scalar() == 0:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        logger.info("042: 已为 %s 添加 %s 列", table, column)
    else:
        logger.info("042: %s.%s 已存在，跳过", table, column)


def upgrade(db):
    _add_column(
        db, "wish_items", "validity_days",
        "INT NULL COMMENT '有效期天数：创建时按 deadline-创建日 计算；重置时据此顺延 deadline'",
    )
    _add_column(
        db, "goal_items", "validity_days",
        "INT NULL COMMENT '有效期天数：创建时按 deadline-创建日 计算；重置时据此顺延 deadline'",
    )
    db.commit()
    logger.info("042: wish_items / goal_items validity_days 迁移完成")


def downgrade(db):
    db.execute(text("ALTER TABLE wish_items DROP COLUMN validity_days"))
    db.execute(text("ALTER TABLE goal_items DROP COLUMN validity_days"))
    db.commit()
    logger.info("042: 已回滚 validity_days 列")
