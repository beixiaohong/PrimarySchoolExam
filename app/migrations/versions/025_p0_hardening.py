"""025 - P0 防刷加固字段

- makeup_cards.last_grant_date：补签卡最近发放日期（替代 updated_at 做每日去重，防误判）
- exam_min_counts.difficulty_min：家长设置的试卷难度下限（基础/提高/拔高），
  防止孩子选「简单」刷分完成任务
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger("migrations")


def _add_column(db, table: str, column: str, ddl_type: str):
    """方言无关的加列（列已存在则跳过，SQLite/MySQL 通用）"""
    bind = db.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    if column in cols:
        return
    db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    logger.info("%s.%s 列已添加", table, column)


def upgrade(db):
    _add_column(db, "makeup_cards", "last_grant_date", "DATE")
    _add_column(db, "exam_min_counts", "difficulty_min", "VARCHAR(10) DEFAULT '基础'")
