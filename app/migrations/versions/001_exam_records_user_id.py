"""001 对齐 exam_records.user_id 列

背景：数据库中 exam_records 表存在 user_id 列，但 model 未声明，
属于历史遗留的"孤儿列"。本迁移将其正式纳入 model 管理，
并为全新数据库补建该列（幂等：列已存在则跳过）。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("migrations")


def upgrade(db):
    # 检查列是否存在（SQLite 的 PRAGMA 查询）
    row = db.execute(text("PRAGMA table_info(exam_records)")).fetchall()
    cols = {r[1] for r in row}
    if "user_id" in cols:
        logger.info("exam_records.user_id 已存在，跳过")
        return
    # 为 exam_records 补充 user_id 列（将历史孤儿列正式纳入 model 管理）
    db.execute(text("ALTER TABLE exam_records ADD COLUMN user_id VARCHAR(64)"))
    logger.info("exam_records 已补充 user_id 列")
