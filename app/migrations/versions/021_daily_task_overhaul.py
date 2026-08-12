"""021: 每日任务改造 — 强制+可选双轨、补签卡

- daily_tasks 增加 task_type 列（mandatory/optional）
- 创建 makeup_cards 表（补签卡余额）
- 创建 makeup_usage_log 表（使用记录）
"""
from sqlalchemy import text


def upgrade(db):
    # daily_tasks 增加 task_type（ALTER TABLE ADD COLUMN 在 SQLite 中如果已存在会报错，用 try 忽略）
    try:
        db.execute(text("ALTER TABLE daily_tasks ADD COLUMN task_type VARCHAR(20) DEFAULT 'mandatory'"))
    except Exception:
        pass  # 列已存在

    # 新建补签卡余额表（makeup_cards）
    db.execute(text("""CREATE TABLE IF NOT EXISTS makeup_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id VARCHAR(50) NOT NULL UNIQUE,
        balance INTEGER DEFAULT 0,
        total_earned INTEGER DEFAULT 0,
        total_used INTEGER DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""))

    # 新建补签卡使用记录表（makeup_usage_log）
    db.execute(text("""CREATE TABLE IF NOT EXISTS makeup_usage_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id VARCHAR(50) NOT NULL,
        target_date DATE NOT NULL,
        used_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )"""))
    # 为补签卡使用记录建 user_id 索引
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_makeup_usage_log_user_id ON makeup_usage_log(user_id)"))
