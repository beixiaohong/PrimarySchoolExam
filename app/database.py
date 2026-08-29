"""数据库连接与会话管理（MySQL 驱动，由 .env 的 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 控制）

会话生命周期：每次 HTTP 请求经 get_db 依赖新建一个 SessionLocal 会话，请求结束 finally 关闭，避免连接泄漏。
建表兜底：init_db 先 Base.metadata.create_all 保证表存在，再跑 _ensure_columns 轻量列迁移补齐新增字段（create_all 不会改已有表）。

说明：本项目已移除 SQLite 支持，数据库统一为 MySQL（生产 / 本地一致）。
"""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import BASE_DIR, DATABASE_URL

# 统一 MySQL 引擎：pool_pre_ping 探活 + pool_recycle 防连接超时（跨长时间空闲连接被服务端断开）
# 池容量：默认 5+10=15 在 AI 类长请求并发下会耗尽（QueuePool TimeoutError 全站卡死），
# 扩至 10+30=40/worker；pool_timeout 15 快速失败避免雪崩排队（需与 MySQL max_connections 匹配）
engine = create_engine(
    DATABASE_URL, echo=False, pool_pre_ping=True, pool_recycle=3600,
    pool_size=10, max_overflow=30, pool_timeout=15,
)

# 创建数据库会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── 采集暂存库（可选）──
# SQLPub 等主库达到上限/不可用时，采集子系统可先把试卷落本地 SQLite 暂存，
# 再用 tools/qb_release.py generate 抽取成脚本、传到线上 apply。
# 不配置 STAGING_DB_URL 时，采集照旧直接写主库 MySQL（向后兼容）。
STAGING_DB_URL = os.environ.get("STAGING_DB_URL")
if STAGING_DB_URL and STAGING_DB_URL.startswith("sqlite:///"):
    # 相对路径解析到项目根目录，避免依赖运行 cwd
    _rel = STAGING_DB_URL[len("sqlite:///"):]
    if not os.path.isabs(_rel):
        STAGING_DB_URL = "sqlite:///" + str(BASE_DIR / _rel)
_staging_engine = None
StagingSessionLocal = None
if STAGING_DB_URL:
    # 确保 SQLite 文件所在目录存在（相对路径已解析到 BASE_DIR 下）
    if STAGING_DB_URL.startswith("sqlite:///"):
        _db_path = STAGING_DB_URL[len("sqlite:///"):]
        _db_dir = os.path.dirname(_db_path)
        if _db_dir:
            os.makedirs(_db_dir, exist_ok=True)
    _staging_engine = create_engine(
        STAGING_DB_URL, connect_args={"check_same_thread": False})
    StagingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_staging_engine)


def collection_session():
    """采集子系统会话：配置了 STAGING_DB_URL 走本地 SQLite 暂存，否则走主库 MySQL。

    让 collect_papers / qb_release generate 在不依赖主库可用性的前提下运行。
    """
    return StagingSessionLocal() if StagingSessionLocal is not None else SessionLocal()


def init_staging_db():
    """采集暂存库建表：仅建 papers / paper_questions 两张采集表（不触碰主库）。

    MySQL 专属的 _ensure_columns 补列逻辑此处不需要——模型本身已含全部列定义。
    """
    if _staging_engine is None:
        return
    from .models.paper import Paper, PaperQuestion
    Base.metadata.create_all(
        bind=_staging_engine, tables=[Paper.__table__, PaperQuestion.__table__])


def init_collection_db():
    """采集子系统建表入口：暂存模式只建本地 SQLite，否则建主库 MySQL。

    暂存模式下完全不连主库，避免主库不可用（如 SQLPub 达上限）时采集中断。
    """
    if _staging_engine is not None:
        init_staging_db()
    else:
        init_db()


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
    # 解析/详解列（与 correct_answer 分离，便于前端展示）
    _ensure_column("paper_questions", "explanation", "TEXT")
    # 回填已有 paper_questions 的 grade/subject（来自所属试卷）
    _backfill_pq_grade_subject()
    # 卡券限期窗口字段（required_within_days 有默认值，cycle_start_date 可空）
    _ensure_column("reward_coupons", "required_within_days", "INT DEFAULT 0")
    _ensure_column("reward_coupons", "cycle_start_date", "VARCHAR(10)")
    # 申诉裁决备注（家长判对/判错时填写，可空）
    _ensure_column("answer_appeals", "note", "TEXT")
    # 普通用户登录会话 token（028_user_token）：VARCHAR 可空、DATETIME 可空
    _ensure_column("users", "token", "VARCHAR(64)")
    _ensure_column("users", "token_expires_at", "DATETIME")
    # 精确答案列（数学判分根因修复：除法/百分数等非整数结果存高精度值，
    # 判分按精确值比对，不再被 2 位小数截断误判，如 10/3 → 3.33333）
    _ensure_column("questions", "exact_answer", "VARCHAR(200) DEFAULT ''")


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
