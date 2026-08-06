"""006 周报表增加家长寄语列

背景：Sprint 3 成长周报 —— 家长在周报页给孩子写寄语，
存到对应周次的 weekly_reports.parent_note，孩子端周报页展示。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    cols = [row[1] for row in db.execute(text("PRAGMA table_info(weekly_reports)")).fetchall()]
    if "parent_note" not in cols:
        db.execute(text("ALTER TABLE weekly_reports ADD COLUMN parent_note VARCHAR(200) DEFAULT ''"))
        logger.info("weekly_reports.parent_note 列已添加")
    else:
        logger.info("weekly_reports.parent_note 已存在，跳过")
