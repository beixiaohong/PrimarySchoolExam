"""022: 修复 daily_tasks 唯一约束 — 改为 (user_id, task_date, task_code)

旧约束: UNIQUE(user_id, task_date, subject)
新约束: UNIQUE(user_id, task_date, task_code)

这样同一用户同一天可以有多个同学科的可选任务。
SQLite 不支持直接修改约束，需要重建表。
"""
from sqlalchemy import text


def upgrade(db):
    db.execute(text("PRAGMA foreign_keys=off"))
    try:
        db.execute(text("ALTER TABLE daily_tasks RENAME TO daily_tasks_old"))
        db.execute(text("""CREATE TABLE daily_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(50) NOT NULL,
            task_date DATE NOT NULL,
            subject VARCHAR(20) NOT NULL,
            task_code VARCHAR(50) NOT NULL,
            title VARCHAR(100) NOT NULL,
            target INTEGER DEFAULT 1,
            progress INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',
            manual BOOLEAN DEFAULT 0,
            task_type VARCHAR(20) DEFAULT 'mandatory',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_date, task_code)
        )"""))
        db.execute(text("CREATE INDEX ix_daily_tasks_user_id ON daily_tasks(user_id)"))
        db.execute(text("CREATE INDEX ix_daily_tasks_task_date ON daily_tasks(task_date)"))
        # 迁移旧数据
        db.execute(text("""INSERT INTO daily_tasks
            (id, user_id, task_date, subject, task_code, title, target, progress, status, manual, task_type, created_at, updated_at)
            SELECT id, user_id, task_date, subject, task_code, title, target, progress, status, manual,
                   COALESCE(task_type, 'mandatory'), created_at, updated_at
            FROM daily_tasks_old"""))
        db.execute(text("DROP TABLE daily_tasks_old"))
    finally:
        db.execute(text("PRAGMA foreign_keys=on"))
