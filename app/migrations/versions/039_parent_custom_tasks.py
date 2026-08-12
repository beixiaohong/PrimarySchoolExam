"""039 家长自定义每日任务：parent_custom_tasks 表（MySQL-only，SQLite 测试跳过）

- parent_custom_tasks：家长定义的自定义每日任务（集成进每日任务强制/可选区，由家长确认完成）
- 旧版「孩子创建、家长确认」的 custom_tasks 表已存在，本迁移新建独立的家长定义表，二者互不干扰

为何 MySQL-only：建表用 INT AUTO_INCREMENT / ENGINE=InnoDB / ON UPDATE
CURRENT_TIMESTAMP / 内联 COMMENT 等 MySQL 专属 DDL，SQLite 不支持。
"""
from sqlalchemy import inspect, text


def upgrade(db):
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())

    if "parent_custom_tasks" not in tables:
        # 新建家长自定义每日任务表 parent_custom_tasks（AUTO_INCREMENT/InnoDB 为 MySQL 专属）
        db.execute(text(
            """
            CREATE TABLE parent_custom_tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                title VARCHAR(100) NOT NULL,
                subject VARCHAR(20) DEFAULT '其他',
                task_type VARCHAR(20) DEFAULT 'optional',
                target INT DEFAULT 1,
                sort_order INT DEFAULT 0,
                active TINYINT(1) DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='家长自定义每日任务'
            """
        ))
        db.commit()
