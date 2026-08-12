"""040 - 补签卡使用记录增加状态机（pending/confirmed/rejected）与任务关联

- makeup_usage_log.status：补签卡使用后的确认状态（孩子发起即扣卡→pending，家长确认→confirmed，拒绝→rejected）
- makeup_usage_log.task_id：孩子用补签卡完成某条每日任务时的关联任务 id（补签某天时为 NULL）

MySQL-only 迁移：SQLite（测试环境）由 Base.metadata.create_all 兜底，本脚本跳过。

为何 MySQL-only：本脚本在 MySQL 生产库为 makeup_usage_log 加 NOT NULL DEFAULT 列并建
索引；SQLite 测试环境表结构由 create_all 兜底，runner 跳过本脚本。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    # 检查 status 列是否已存在
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'makeup_usage_log' AND COLUMN_NAME = 'status'"
    ))
    if result.scalar() == 0:
        # 新增 status 列：默认 confirmed（历史「补签某天」记录即视为已生效）
        db.execute(text(
            "ALTER TABLE makeup_usage_log "
            "ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'confirmed'"
        ))
        logger.info("040: 已添加 status 列")
    else:
        logger.info("040: status 列已存在，跳过")

    # 检查 task_id 列是否已存在
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'makeup_usage_log' AND COLUMN_NAME = 'task_id'"
    ))
    if result.scalar() == 0:
        # 新增 task_id 列：关联每日任务（补签卡完成任意任务时填写）
        db.execute(text(
            "ALTER TABLE makeup_usage_log ADD COLUMN task_id INT NULL"
        ))
        logger.info("040: 已添加 task_id 列")
    else:
        logger.info("040: task_id 列已存在，跳过")

    # 检查索引是否已存在
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'makeup_usage_log' AND INDEX_NAME = 'ix_makeup_usage_log_task_id'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "CREATE INDEX ix_makeup_usage_log_task_id "
            "ON makeup_usage_log (task_id)"
        ))
        logger.info("040: 已创建索引")
    else:
        logger.info("040: 索引已存在，跳过")
    db.commit()
    logger.info("040: makeup_usage_log 迁移完成")


def downgrade(db):
    db.execute(text("ALTER TABLE makeup_usage_log DROP COLUMN task_id"))
    db.execute(text("ALTER TABLE makeup_usage_log DROP COLUMN status"))
    db.commit()
    logger.info("040: makeup_usage_log 已回滚 status / task_id 列")
