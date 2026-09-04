"""061 - 教材版本表新增 region 省份代码字段

背景（S6 IP 地理位置 / 教材 / 地区 / 天气）：
- TextbookVersion 加 region 字段（中国省份代码，chinaAdminCode 前 2 位；
  空字符串 = 全国通用；用于按用户 IP 解析的省份自动匹配本地教材版本）。
- 索引：idx_region_subject_grade_enabled 加速 resolve 查询（用户省份 → 该省版本）。
- 后台 CRUD：admin/textbooks.py 同步支持 region 字段。

幂等：information_schema.COLUMNS / STATISTICS 检测，MySQL-only。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    bind = db.get_bind()

    # ── 1) textbook_versions.region 列 ──
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'textbook_versions' "
        "AND COLUMN_NAME = 'region'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "ALTER TABLE textbook_versions ADD COLUMN region VARCHAR(8) NOT NULL DEFAULT '' "
            "COMMENT '省份代码（chinaAdminCode 前 2 位；空=全国通用）' "
            "AFTER enabled"
        ))
        logger.info("061: 已为 textbook_versions 添加 region 列")
    else:
        logger.info("061: textbook_versions.region 已存在，跳过")

    # ── 2) 复合索引 (region, subject, grade, enabled) 用于 resolve 查询 ──
    result = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'textbook_versions' "
        "AND INDEX_NAME = 'idx_region_subject_grade'"
    ))
    if result.scalar() == 0:
        db.execute(text(
            "CREATE INDEX idx_region_subject_grade ON textbook_versions "
            "(region, subject, grade, enabled)"
        ))
        logger.info("061: 已创建 idx_region_subject_grade 索引")
    else:
        logger.info("061: idx_region_subject_grade 已存在，跳过")

    db.commit()
    logger.info("061: textbook_versions.region 字段 + 索引就绪")
