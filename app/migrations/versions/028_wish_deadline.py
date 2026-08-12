"""028: 心愿单增加截止日期

wish_items 增加：
- deadline: 截止日期，超过后未完成的心愿自动过期（expired）
"""
from sqlalchemy import text


def upgrade(db):
    try:
        # 为心愿单新增截止日期列 deadline（超时未完成自动过期为 expired）
        db.execute(text("ALTER TABLE wish_items ADD COLUMN deadline DATE"))
    except Exception:
        pass  # 列已存在
