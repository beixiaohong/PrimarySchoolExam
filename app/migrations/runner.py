"""迁移执行器：按版本号顺序执行未应用的迁移脚本

MySQL 基线策略：001-025 旧迁移均为 SQLite 方言（建表/重建表/种子数据），
MySQL 侧改由 Base.metadata.create_all 直接建表，启动时把存量迁移版本
预置为已执行；此后的新迁移需用方言兼容写法（两种驱动都会执行）。
"""
import importlib
import logging
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Table, text
from sqlalchemy.orm import Session

from ..config import DB_DRIVER
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


def run_migrations() -> list:
    """执行所有未应用的迁移脚本，返回本次应用的版本列表"""
    # 确保版本表存在
    Base.metadata.create_all(bind=engine, tables=[MIGRATIONS_TABLE])

    versions = _list_versions()

    # MySQL 基线：存量 SQLite 方言迁移不执行，直接标记为已应用
    if DB_DRIVER != "sqlite":
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
