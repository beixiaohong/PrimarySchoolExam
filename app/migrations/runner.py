"""迁移执行器：按版本号顺序执行未应用的迁移脚本

MySQL-only 基线策略：001-025 旧迁移均为 SQLite 方言（建表/重建表/种子数据），
MySQL 侧不执行，启动时直接预置为「已执行」；表结构由 Base.metadata.create_all
（init_db 中）统一建立。026+ 迁移（含 029 起的 MySQL-only）在启动时按顺序
真实执行（均幂等）。

本项目已移除 SQLite 支持，数据库统一为 MySQL。
"""
import importlib
import logging
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Table, text
from sqlalchemy.orm import Session

from ..database import Base, engine

logger = logging.getLogger("migrations")

# 版本记录表（模型无关，直接声明，避免与业务 model 耦合）
MIGRATIONS_TABLE = Table(
    "schema_migrations",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("version", String(100), nullable=False, unique=True, comment="脚本名，如 001_exam_records_user_id"),
    Column("applied_at", DateTime, default=datetime.now),
)

VERSIONS_DIR = "app.migrations.versions"

# 026 起为幂等迁移（inspector/checkfirst/try-except），MySQL 下顺序真实执行；历史 001-025 基线预置为已执行。


def run_migrations() -> list:
    """执行所有未应用的迁移脚本，返回本次应用的版本列表"""
    # 确保版本表存在
    Base.metadata.create_all(bind=engine, tables=[MIGRATIONS_TABLE])

    versions = _list_versions()

    # MySQL 基线：001-025 为历史 SQLite 方言迁移，MySQL 侧不执行，
    # 直接预置为「已执行」，避免重复建表/种子；表结构由 create_all 兜底。
    with Session(engine) as db:
        applied_now = {row[0] for row in db.execute(text("SELECT version FROM schema_migrations"))}
        legacy = [v for v in versions if v <= "025_p0_hardening"]
        for v in legacy:
            if v not in applied_now:
                logger.info("MySQL 基线：预置迁移版本 %s 为已执行", v)
                db.execute(
                    text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                    {"v": v, "t": datetime.now()},
                )
        db.commit()

    applied = set()
    with Session(engine) as db:
        for row in db.execute(text("SELECT version FROM schema_migrations")):
            applied.add(row[0])

    executed = []
    for name in versions:
        if name in applied:
            continue
        module = importlib.import_module(f"{VERSIONS_DIR}.{name}")
        with Session(engine) as db:
            logger.info("执行迁移: %s", name)
            module.upgrade(db)
            db.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :t)"),
                {"v": name, "t": datetime.now()},
            )
            db.commit()
        executed.append(name)

    return executed


def _list_versions() -> list:
    """扫描 versions 包，按编号排序返回脚本名列表"""
    import os
    import pkgutil

    names = []
    pkg = importlib.import_module(VERSIONS_DIR)
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        names.append(info.name)
    return sorted(names)
