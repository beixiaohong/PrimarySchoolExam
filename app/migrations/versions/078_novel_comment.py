"""078 - 小说评论表 db_novel_comments

小说站社区（优化方案 #8 增强）：读者书评 / 短评，支撑书籍评论区。
- status：active=展示 / deleted=已删除（软删，保留行避免统计抖动）
- chapter_idx=0 表示「全书短评」；>0 表示针对某章/段的评论

幂等：information_schema.TABLES 检测，已存在则跳过。MySQL-only。
（本项目迁移为自定义 runner，签名 upgrade(db)，不使用 alembic。）
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
    if _table_exists(db, "db_novel_comments"):
        logger.info("078: 表 db_novel_comments 已存在，跳过")
        return
    db.execute(text(
        "CREATE TABLE db_novel_comments ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " user_id VARCHAR(64) NOT NULL,"
        " novel_id INT NOT NULL,"
        " chapter_idx INT NOT NULL DEFAULT 0,"
        " content VARCHAR(500) NOT NULL,"
        " status VARCHAR(16) NOT NULL DEFAULT 'active',"
        " like_count INT NOT NULL DEFAULT 0,"
        " created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (id),"
        " INDEX idx_nc_novel_created (novel_id, created_at),"
        " INDEX idx_nc_user (user_id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        " COMMENT='小说站社区：读者书评/短评'"
    ))
    db.commit()
    logger.info("078: 已创建表 db_novel_comments")
