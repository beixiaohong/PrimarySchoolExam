"""041 - 用户表增加 token 列（Bearer 鉴权）

users 表新增：
- token: 登录会话 token
- token_expires_at: token 过期时间
"""
import logging
from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    # 检查 token 列是否已存在
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'token'"
    ))
    if result.scalar() == 0:
        db.execute(text("ALTER TABLE users ADD COLUMN token VARCHAR(64) NULL"))
        db.execute(text("CREATE INDEX ix_users_token ON users (token)"))
        logger.info("041: 已添加 token 列和索引")
    else:
        logger.info("041: token 列已存在，跳过")

    # 检查 token_expires_at 列是否已存在
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'token_expires_at'"
    ))
    if result.scalar() == 0:
        db.execute(text("ALTER TABLE users ADD COLUMN token_expires_at DATETIME NULL"))
        logger.info("041: 已添加 token_expires_at 列")
    else:
        logger.info("041: token_expires_at 列已存在，跳过")

    db.commit()
    logger.info("041: users 表 token 迁移完成")


def downgrade(db):
    db.execute(text("ALTER TABLE users DROP COLUMN token_expires_at"))
    db.execute(text("ALTER TABLE users DROP COLUMN token"))
    db.commit()
    logger.info("041: users 表 token 列已回滚")
