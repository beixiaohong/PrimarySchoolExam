"""046 - 补 answer_appeals.attempt_id 列（申诉精确定位做题记录）

背景：申诉改判（_approve_exam）此前只能用 user_id + question_id 模糊定位
「该题最新一条判错记录」，存在误改判风险；孩子申诉时前端实际持有
交卷返回的 attempt_id（做题记录号），用 (attempt_id, question_id) 即可
唯一定位那条作答，无需依赖作答文本匹配。

修复：幂等 ADD COLUMN（information_schema 检测，已存在则跳过）。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'answer_appeals' "
        "AND COLUMN_NAME = 'attempt_id'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "ALTER TABLE answer_appeals ADD COLUMN attempt_id INT NULL "
            "COMMENT 'exam：做题记录 id（attempt_id，精确改判定位）'"
        ))
        logger.info("046: 已为 answer_appeals 添加 attempt_id 列")
    else:
        logger.info("046: answer_appeals.attempt_id 已存在，跳过")
