"""040 - 补签卡使用记录增加状态机（pending/confirmed/rejected）与任务关联

- makeup_usage_log.status：补签卡使用后的确认状态（孩子发起即扣卡→pending，家长确认→confirmed，拒绝→rejected）
- makeup_usage_log.task_id：孩子用补签卡完成某条每日任务时的关联任务 id（补签某天时为 NULL）

MySQL-only 迁移：SQLite（测试环境）由 Base.metadata.create_all 兜底，本脚本跳过。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    # 新增 status 列：默认 confirmed（历史「补签某天」记录即视为已生效）
    db.execute(text(
        "ALTER TABLE makeup_usage_log "
        "ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'confirmed'"
    ))
    # 新增 task_id 列：关联每日任务（补签卡完成任意任务时填写）
    db.execute(text(
        "ALTER TABLE makeup_usage_log ADD COLUMN task_id INT NULL"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_makeup_usage_log_task_id "
        "ON makeup_usage_log (task_id)"
    ))
    db.commit()
    logger.info("040: makeup_usage_log 已增加 status / task_id 列")


def downgrade(db):
    db.execute(text("ALTER TABLE makeup_usage_log DROP COLUMN task_id"))
    db.execute(text("ALTER TABLE makeup_usage_log DROP COLUMN status"))
    db.commit()
    logger.info("040: makeup_usage_log 已回滚 status / task_id 列")
