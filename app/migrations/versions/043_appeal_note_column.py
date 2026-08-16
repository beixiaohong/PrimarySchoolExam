"""043 - 补 answer_appeals.note 列（家长裁决备注）

背景：013 迁移建 answer_appeals 表时遗漏了 note 列，但模型 AnswerAppeal 和
decide_appeal 端点都在使用它。导致家长点击「确认做对了 / 维持判错」时，
db.commit() 因 UPDATE 含不存在的 note 列而报 MySQL "Unknown column" 错误，
异常被 try/except 静默吞掉 → 事务回滚 → 裁决结果（status 变更）未持久化。
前端收到成功响应后移除列表项，但刷新后申诉重新出现——表现为「点击无响应」。

修复：幂等 ADD COLUMN（information_schema 检测，已存在则跳过）。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'answer_appeals' "
        "AND COLUMN_NAME = 'note'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "ALTER TABLE answer_appeals ADD COLUMN note TEXT NULL "
            "COMMENT '家长裁决备注（可选）'"
        ))
        logger.info("043: 已为 answer_appeals 添加 note 列")
    else:
        logger.info("043: answer_appeals.note 已存在，跳过")
