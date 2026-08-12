"""数据库连接与会话管理（SQLite / MySQL 双驱动，由 .env 的 DB_DRIVER 控制）"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import DATABASE_URL, DB_DRIVER

# SQLite 需要 check_same_thread；MySQL 无需额外参数
if DB_DRIVER == "sqlite":
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
else:
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=3600)

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


def random_order():
    """随机排序函数（方言兼容）：SQLite 用 random()，MySQL 用 rand()"""
    from sqlalchemy import func
    return func.rand() if DB_DRIVER != "sqlite" else func.random()


def _ensure_columns():
    """轻量迁移：为已有表补充新增列（create_all 不会改已有表）"""
    # image_base64 跨 dialect 补齐（MySQL 侧没有覆盖该列的迁移脚本）。
    # 注意：MySQL 的 TEXT/MEDIUMTEXT 列不允许有 DEFAULT 值，故 MySQL 侧不带 DEFAULT。
    _ensure_column(
        "questions", "image_base64",
        "MEDIUMTEXT" if DB_DRIVER == "mysql" else "TEXT DEFAULT ''",
    )
    # paper_questions 冗余年级/学科列（便于按年级+学科抽题，不依赖 JOIN）。
    # VARCHAR(20) 双方言均允许 DEFAULT ''，故统一带 DEFAULT。
    _ensure_column("paper_questions", "grade", "VARCHAR(20) DEFAULT ''")
    _ensure_column("paper_questions", "subject", "VARCHAR(20) DEFAULT ''")
    # 回填已有 paper_questions 的 grade/subject（来自所属试卷）
    _backfill_pq_grade_subject()
    if DB_DRIVER != "sqlite":
        return  # 其余轻量迁移仅 SQLite 需要；MySQL 侧由迁移脚本接管
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


def _backfill_pq_grade_subject():
    """将 paper_questions 的 grade/subject 从未填行回填为所属试卷的年级/学科。"""
    with engine.connect() as conn:
        try:
            if DB_DRIVER == "mysql":
                conn.execute(text(
                    "UPDATE paper_questions pq JOIN papers p ON pq.paper_id = p.id "
                    "SET pq.grade = p.grade, pq.subject = p.subject "
                    "WHERE pq.grade = '' OR pq.grade IS NULL"
                ))
            else:
                conn.execute(text(
                    "UPDATE paper_questions "
                    "SET grade = (SELECT p.grade FROM papers p WHERE p.id = paper_questions.paper_id), "
                    "subject = (SELECT p.subject FROM papers p WHERE p.id = paper_questions.paper_id) "
                    "WHERE grade = '' OR grade IS NULL"
                ))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


def _ensure_column(table, column, definition):
    """幂等地为指定表补齐一列（跨 dialect 安全）：直接尝试 ALTER，忽略已存在错误。"""
    with engine.connect() as conn:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
            conn.commit()
        except Exception:
            # 列已存在或其它可忽略错误（如 dialect 差异）
            try:
                conn.rollback()
            except Exception:
                pass


def init_db():
    """创建所有表 + 轻量迁移"""
    from . import models  # noqa: F401 确保模型被导入
    # 初始化数据库表结构
    Base.metadata.create_all(bind=engine)
    # 执行列级增量迁移
    _ensure_columns()