"""030 教学进度表（MySQL-only，SQLite 测试环境跳过）

每用户每科一条：当前词书 + 当前单元，驱动背诵/听写/出卷的课堂同步。

为何 MySQL-only：DDL 使用 AUTO_INCREMENT、ENGINE=InnoDB、内联 COLUMN/COMMENT
等 MySQL 专属写法，SQLite 不支持，故测试环境跳过。
"""
from sqlalchemy import inspect, text


def upgrade(db):
    insp = inspect(db.bind)
    if "teaching_progress" not in insp.get_table_names():
        # 新建教学进度表 teaching_progress（每用户每科一条，AUTO_INCREMENT/InnoDB 为 MySQL 专属）
        db.execute(text("""
            CREATE TABLE teaching_progress (
                id INTEGER NOT NULL AUTO_INCREMENT,
                user_id VARCHAR(64) NOT NULL COMMENT '用户 ID',
                subject VARCHAR(20) NOT NULL COMMENT '学科',
                book_id INTEGER NULL COMMENT '英语词书 ID（其他学科可空）',
                chapter VARCHAR(100) NOT NULL DEFAULT '' COMMENT '当前章节/单元，如 Unit 3',
                updated_at DATETIME NULL COMMENT '更新时间',
                PRIMARY KEY (id),
                UNIQUE KEY uq_progress_user_subject (user_id, subject)
            ) COMMENT='教学进度：每用户每科一条'
        """))
    idx = {i["name"] for i in insp.get_indexes("teaching_progress")}
    if "ix_teaching_progress_user_id" not in idx:
        # 建 user_id 索引加速按用户查询
        db.execute(text("CREATE INDEX ix_teaching_progress_user_id ON teaching_progress (user_id)"))
