"""049 - users.is_active 列（账号停用/启用）

背景（需求4：丰富后台用户管理）：管理员可停用违规/弃用账号，
停用后该账号无法登录（auth 登录与 require_user 鉴权均校验）。

幂等：information_schema 检测，已存在则跳过。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
        "AND COLUMN_NAME = 'is_active'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 "
            "COMMENT '账号状态：1=正常 / 0=已停用（停用后无法登录）'"
        ))
        logger.info("049: 已为 users 添加 is_active 列")
    else:
        logger.info("049: users.is_active 已存在，跳过")
