"""031 problem_types 增加教材章节映射列（MySQL-only，SQLite 测试环境跳过）

为数学出卷「同步模式」预留：textbook_chapter 记录题型对应的教材章节，
具体人教版章节映射数据后续人工补充。
"""
from sqlalchemy import inspect, text


def upgrade(db):
    insp = inspect(db.bind)
    cols = {c["name"] for c in insp.get_columns("problem_types")}
    if "textbook_chapter" not in cols:
        db.execute(text(
            "ALTER TABLE problem_types ADD COLUMN textbook_chapter VARCHAR(100) NOT NULL DEFAULT '' COMMENT '教材章节映射'"
        ))
