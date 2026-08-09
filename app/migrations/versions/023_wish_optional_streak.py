"""023: 许愿系统升级 — 支持连续n天每天m个可选任务

wish_items 增加：
- wish_type: task_count(旧) / optional_streak(新)
- daily_target: 每天需完成的可选任务数
- last_progress_date: 上次进度递增日期
"""
from sqlalchemy import text


def upgrade(db):
    for col, col_type, default in [
        ("wish_type", "VARCHAR(20) DEFAULT 'task_count'", "'task_count'"),
        ("daily_target", "INTEGER DEFAULT 0", "0"),
        ("last_progress_date", "DATE", "NULL"),
    ]:
        try:
            db.execute(text(f"ALTER TABLE wish_items ADD COLUMN {col} {col_type}"))
        except Exception:
            pass  # 列已存在
