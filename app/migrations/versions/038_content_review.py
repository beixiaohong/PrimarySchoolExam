"""038 多 AI 校对机制：content_reviews 表 + review_status 列（MySQL-only，SQLite 测试跳过）

- content_reviews 表（多 AI 联合校对记录）
- middle_questions 加 review_status 列（reading_passages 的 review_status 已在 036 建表时包含，幂等跳过）
"""
from sqlalchemy import inspect, text


def upgrade(db):
    insp = inspect(db.bind)
    tables = set(insp.get_table_names())

    # ── 1. content_reviews 表 ──
    if "content_reviews" not in tables:
        db.execute(text(
            """
            CREATE TABLE content_reviews (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content_type VARCHAR(40) NOT NULL,
                content_id INT NOT NULL,
                provider VARCHAR(20) DEFAULT '',
                model VARCHAR(40) DEFAULT '',
                verdict VARCHAR(20) DEFAULT 'pass',
                comment TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX (content_type, content_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='多 AI 联合校对记录'
            """
        ))

    # ── 2. review_status 列（已存在则跳过）──
    if "middle_questions" in tables:
        _add_column(db, "middle_questions", "review_status", "VARCHAR(20) DEFAULT 'pending'")
    if "reading_passages" in tables:
        # 036 已含该列，这里幂等补，存在则忽略
        _add_column(db, "reading_passages", "review_status", "VARCHAR(20) DEFAULT 'pending'")


def _add_column(db, table, column, definition):
    try:
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
