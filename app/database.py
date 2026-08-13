"""数据库连接与会话管理（MySQL 驱动，由 .env 的 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 控制）

会话生命周期：每次 HTTP 请求经 get_db 依赖新建一个 SessionLocal 会话，请求结束 finally 关闭，避免连接泄漏。
建表兜底：init_db 先 Base.metadata.create_all 保证表存在，再跑 _ensure_columns 轻量列迁移补齐新增字段（create_all 不会改已有表）。

说明：本项目已移除 SQLite 支持，数据库统一为 MySQL（生产 / 本地一致）。
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import DATABASE_URL

# 统一 MySQL 引擎：pool_pre_ping 探活 + pool_recycle 防连接超时（跨长时间空闲连接被服务端断开）
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
    """随机排序函数（MySQL 用 rand()）"""
    from sqlalchemy import func
    return func.rand()


def _ensure_columns():
    """轻量迁移：为已有表补充新增列（create_all 不会改已有表）

    仅保留 MySQL 侧需要的安全补列；列已存在时 _ensure_column 靠异常兜底跳过，幂等。
    """
    # image_base64 跨 dialect 补齐（MySQL 侧用 MEDIUMTEXT，无 DEFAULT）
    _ensure_column(
        "questions", "image_base64",
        "MEDIUMTEXT",
    )
    # paper_questions 冗余年级/学科列（便于按年级+学科抽题，不依赖 JOIN）
    _ensure_column("paper_questions", "grade", "VARCHAR(20) DEFAULT ''")
    _ensure_column("paper_questions", "subject", "VARCHAR(20) DEFAULT ''")
    # 回填已有 paper_questions 的 grade/subject（来自所属试卷）
    _backfill_pq_grade_subject()


def _backfill_pq_grade_subject():
    """将 paper_questions 的 grade/subject 从未填行回填为所属试卷的年级/学科。"""
    with engine.connect() as conn:
        try:
            # MySQL 支持 UPDATE ... JOIN，一次性回填更高效
            conn.execute(text(
                "UPDATE paper_questions pq JOIN papers p ON pq.paper_id = p.id "
                "SET pq.grade = p.grade, pq.subject = p.subject "
                "WHERE pq.grade = '' OR pq.grade IS NULL"
            ))
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


def _ensure_column(table, column, definition):
    """幂等地为指定表补齐一列：直接尝试 ALTER，忽略已存在错误。"""
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
