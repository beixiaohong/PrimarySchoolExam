"""024 - 新建 custom_tasks 表（孩子自定义任务，家长确认）"""
from sqlalchemy import text


def upgrade(db):
    # 新建孩子自定义任务表（孩子创建，家长确认）
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS custom_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(50) NOT NULL,
            title VARCHAR(100) NOT NULL,
            subject VARCHAR(20) DEFAULT '其他',
            status VARCHAR(20) DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            confirmed_at DATETIME
        )
    """))
    # 建 user_id 索引加速按用户查询
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_custom_tasks_user_id ON custom_tasks(user_id)"
    ))
