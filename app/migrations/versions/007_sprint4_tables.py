"""Sprint 4 建表：挑战赛纪录 + 小老师讲解记录"""
from sqlalchemy import Column, Date, DateTime, Integer, String, Text, text

TABLES = {
    "challenge_records": """
        CREATE TABLE IF NOT EXISTS challenge_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(64) NOT NULL,
            kind VARCHAR(20) NOT NULL,
            correct INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "teaching_records": """
        CREATE TABLE IF NOT EXISTS teaching_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(64) NOT NULL,
            record_kind VARCHAR(20) NOT NULL,
            record_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            note TEXT DEFAULT '',
            status VARCHAR(20) DEFAULT 'pending',
            answer_text TEXT DEFAULT '',
            is_correct INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            answered_at DATETIME,
            graded_at DATETIME,
            due_date DATE,
            recheck_status VARCHAR(20)
        )
    """,
}


def upgrade(db):
    for name, ddl in TABLES.items():
        db.execute(text(ddl))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_challenge_records_user ON challenge_records(user_id)"))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_teaching_records_user ON teaching_records(user_id)"))
