"""SQLite 数据库连接与会话管理"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import DATABASE_URL

# 创建 SQLAlchemy 引擎实例
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 多线程需要
    echo=False,
)

# 创建数据库会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有模型的基类"""
    pass


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns():
    """轻量迁移：为已有表补充新增列（SQLite create_all 不会改已有表）"""
    # 定义需要检查并补齐的列变更列表
    migrations = [
        # (表名, 列名, 定义)
        ("study_errors", "cause", "VARCHAR(20) DEFAULT ''"),
        ("wrong_records", "cause", "VARCHAR(20) DEFAULT ''"),
        ("study_errors", "correct_streak", "INTEGER DEFAULT 0"),
        ("wrong_records", "correct_streak", "INTEGER DEFAULT 0"),
    ]
    with engine.connect() as conn:
        for table, column, definition in migrations:
            # 查询当前表已存在的列名
            cols = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
            # 如果目标列不存在，则执行 ALTER TABLE 语句进行添加
            if column not in cols:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                ))
                conn.commit()


def init_db():
    """创建所有表 + 轻量迁移"""
    from . import models  # noqa: F401 确保模型被导入
    # 初始化数据库表结构
    Base.metadata.create_all(bind=engine)
    # 执行列级增量迁移
    _ensure_columns()