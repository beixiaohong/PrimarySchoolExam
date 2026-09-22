"""077 - 小说书签表 db_novel_bookmarks

小说站增强：补「书签」功能（计划中唯一真缺口；目录/搜索/进度续读/主题/书架已具备）。
读者在阅读器里给某一章/段打书签并可附便签，便于跨设备回看与跳转。

同一 (user_id, novel_id, chapter_idx) 唯一，便于「在同一章再次标记 = 更新便签」
而不会产生重复书签。

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
    if _table_exists(db, "db_novel_bookmarks"):
        logger.info("077: 表 db_novel_bookmarks 已存在，跳过")
        return
    db.execute(text(
        "CREATE TABLE db_novel_bookmarks ("
        " id BIGINT NOT NULL AUTO_INCREMENT,"
        " user_id VARCHAR(64) NOT NULL,"
        " novel_id INT NOT NULL,"
        " chapter_idx INT NOT NULL DEFAULT 1,"
        " note VARCHAR(500) NOT NULL DEFAULT '',"
        " created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        " updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
        " PRIMARY KEY (id),"
        " UNIQUE KEY uq_bookmark_user_novel_idx (user_id, novel_id, chapter_idx),"
        " INDEX idx_bm_user (user_id),"
        " INDEX idx_bm_novel (novel_id)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        " COMMENT='小说书签：读者在章/段做的标记'"
    ))
    db.commit()
    logger.info("077: 已创建表 db_novel_bookmarks")
