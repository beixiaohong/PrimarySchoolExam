"""076 - 智能推题练习记录表 mastery_practice

MVP#1「掌握度模型 + 知识点图谱」闭环所需：用户针对「智能推题」推荐的薄弱知识点
题目作答后，记录到 mastery_practice；mastery_store.build_answer_records 将其并入
掌握度重算输入（与真实考试作答 AttemptAnswer 同等对待），实现「薄弱点 → 推题 → 练
→ 掌握度更新」闭环，避免掌握度功能空转。

幂等：information_schema.TABLES 检测，已存在则跳过。MySQL-only。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def _table_exists(db, name: str) -> bool:
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :n"
    ), {"n": name}).scalar()
    return (row or 0) > 0


def upgrade(db):
    if _table_exists(db, "mastery_practice"):
        logger.info("076: 表 mastery_practice 已存在，跳过")
        return
    db.execute(text(
        "CREATE TABLE mastery_practice ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " user_id VARCHAR(64) NOT NULL,"
        " kp_id INT NOT NULL DEFAULT 0,"
        " question_id INT NOT NULL,"
        " is_correct TINYINT(1) NOT NULL DEFAULT 0,"
        " duration_ms INT NOT NULL DEFAULT 0,"
        " difficulty INT NOT NULL DEFAULT 3,"
        " answered_at DATETIME NOT NULL,"
        " created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (id),"
        " INDEX idx_mp_user_kp (user_id, kp_id),"
        " INDEX idx_mp_user_q (user_id, question_id),"
        " INDEX idx_mp_q (question_id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        " COMMENT='智能推题练习记录：闭环驱动掌握度重算'"
    ))
    db.commit()
    logger.info("076: 已创建表 mastery_practice")
