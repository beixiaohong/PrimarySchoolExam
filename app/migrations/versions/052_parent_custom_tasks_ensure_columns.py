"""052 幂等补 parent_custom_tasks 表缺列（线上 500 修复）

背景：
- 039 迁移用 `if "parent_custom_tasks" not in tables: CREATE TABLE ...` 建表，
  仅在表完全不存在时生效；若线上表是 039 之前手工建的早期版本（缺 sort_order/active 等列），
  039 会跳过 CREATE → 表保持缺列状态。
- 当前模型 ParentCustomTask INSERT 显式含 sort_order/active 等列（含 default=0/True），
  缺列时报 MySQL 1054 Unknown column → 500 Internal Server Error。

修复：
- 幂等检查 information_schema.COLUMNS，缺则 ALTER TABLE ADD COLUMN ... DEFAULT ...
- 兼容 MySQL 5.7/8.0（不用 IF NOT EXISTS 关键字，5.7 不支持）
- SQLite 测试环境跳过（无 information_schema.COLUMNS 视图差异，MySQL-only）

执行时机：deploy.sh 重启时由 run_migrations() 自动跑 026+ 真实迁移。
"""
import logging
from sqlalchemy import inspect, text

logger = logging.getLogger("migrations")


# 表名 + 期望列定义（与 app/models/parent_custom_task.py 一一对应）
TABLE = "parent_custom_tasks"
EXPECTED_COLUMNS = [
    # (column_name, column_type_ddl, default_value, nullable)
    ("id",          "INT AUTO_INCREMENT PRIMARY KEY", None,        False),
    ("user_id",     "VARCHAR(50) NOT NULL",            None,        False),
    ("title",       "VARCHAR(100) NOT NULL",           None,        False),
    ("subject",     "VARCHAR(20) DEFAULT '其他'",       "其他",       False),
    ("task_type",   "VARCHAR(20) DEFAULT 'optional'",  "optional",   False),
    ("target",      "INT DEFAULT 1",                   "1",          False),
    ("sort_order",  "INT DEFAULT 0",                   "0",          False),
    ("active",      "TINYINT(1) DEFAULT 1",            "1",          False),
    ("created_at",  "DATETIME DEFAULT CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP", False),
    ("updated_at",  "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
                                                            "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP", False),
]


def upgrade(db):
    """幂等补列：缺则 ADD COLUMN，有则跳过；表不存在则不处理（039 负责建表）"""
    insp = inspect(db.bind)
    if TABLE not in set(insp.get_table_names()):
        logger.info("052: %s 表不存在，跳过（由 039 迁移负责建表）", TABLE)
        return

    # 查现有所列（information_schema.COLUMNS 跨方言统一）
    existing = {row[0] for row in db.execute(text("""
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
    """), {"t": TABLE}).fetchall()}

    bind_name = db.bind.dialect.name
    if bind_name != "mysql":
        logger.info("052: 非 MySQL 方言（%s），跳过", bind_name)
        return

    added = []
    for col_name, col_type, default_val, _nullable in EXPECTED_COLUMNS:
        if col_name in existing:
            continue
        # 主键 id 一般不会缺；如缺则报"already exists"——直接 try 容错
        ddl = f"ALTER TABLE {TABLE} ADD COLUMN {col_name} {col_type}"
        try:
            db.execute(text(ddl))
            added.append(col_name)
            logger.info("052: ADD COLUMN %s.%s (%s)", TABLE, col_name, col_type)
        except Exception as e:
            # 容错：列已存在/主键冲突等（极少见，理论上 information_schema 已过滤）
            logger.warning("052: ADD COLUMN %s.%s 失败（忽略）：%s", TABLE, col_name, e)
    db.commit()

    if added:
        logger.info("052: %s 已补列：%s", TABLE, ", ".join(added))
    else:
        logger.info("052: %s 表结构与模型一致，无需补列", TABLE)
