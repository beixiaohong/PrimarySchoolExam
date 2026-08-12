"""029 classical_texts 增加学期字段（MySQL-only，SQLite 测试环境跳过）

古诗文按学期解锁：semester=上/下/全，存量数据默认「全」两学期均可背。

为何 MySQL-only：列定义使用了 MySQL 专属的内联 COLUMN COMMENT 语法与
NOT NULL DEFAULT，SQLite 不支持列级 COMMENT，故测试环境直接跳过、由 create_all 兜底。
"""
from sqlalchemy import inspect, text


def upgrade(db):
    insp = inspect(db.bind)
    cols = {c["name"] for c in insp.get_columns("classical_texts")}
    if "semester" not in cols:
        # classical_texts 新增 semester 列：适用学期（上/下/全），内联 COMMENT 为 MySQL 语法
        db.execute(text(
            "ALTER TABLE classical_texts ADD COLUMN semester VARCHAR(10) NOT NULL DEFAULT '全' COMMENT '适用学期：上/下/全'"
        ))
