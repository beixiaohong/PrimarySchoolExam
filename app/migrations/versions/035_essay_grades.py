"""035 作文批改评分卡表（MySQL-only，SQLite 测试环境靠 create_all 建表）

幂等：表已存在则跳过。
"""
from sqlalchemy import inspect, text


def upgrade(db):
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())
    if "essay_grades" not in tables:
        db.execute(text(
            """
            CREATE TABLE essay_grades (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                subject VARCHAR(20) NOT NULL,
                grade INT NOT NULL DEFAULT 6,
                topic VARCHAR(200) NOT NULL DEFAULT '',
                content TEXT,
                score_json TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX (user_id),
                INDEX (subject)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作文批改评分卡'
            """
        ))
