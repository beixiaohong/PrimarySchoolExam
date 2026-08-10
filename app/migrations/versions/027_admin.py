"""027_admin：管理后台（admins / admin_operation_logs / system_config + 初始管理员）

方言兼容写法（SQLite/MySQL 都会执行）：
- 独立 MetaData + checkfirst 建表；
- 初始管理员 admin / 环境变量 ADMIN_INIT_PASSWORD（默认 Admin@123），pbkdf2 与 parent.py 同格式。
"""
import hashlib
import os
import secrets
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, Text, text,
)

PBKDF2_ITER = 120_000


def _hash_pwd(pwd: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt.encode(), PBKDF2_ITER)
    return f"pbkdf2${PBKDF2_ITER}${salt}${dk.hex()}"


def upgrade(db):
    conn = db.connection()

    meta = MetaData()
    Table(
        "admins", meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("username", String(50), nullable=False, unique=True),
        Column("password_hash", String(128), nullable=False),
        Column("role", String(20), nullable=False),
        Column("token", String(64), nullable=True),
        Column("token_expires_at", DateTime, nullable=True),
        Column("last_login_at", DateTime, nullable=True),
        Column("created_at", DateTime, nullable=False),
    )
    Table(
        "admin_operation_logs", meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("admin", String(50), nullable=False),
        Column("action", String(50), nullable=False),
        Column("target", String(64), nullable=False),
        Column("detail", Text, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    Table(
        "system_config", meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("key", String(80), nullable=False, unique=True),
        Column("value", Text, nullable=False),
        Column("updated_by", String(50), nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )
    meta.create_all(bind=conn, checkfirst=True)

    # 初始管理员（幂等：仅表为空时插入，兼容 create_all 先建表的基线策略）
    count = conn.execute(text("SELECT COUNT(*) FROM admins")).scalar()
    if not count:
        pwd = os.environ.get("ADMIN_INIT_PASSWORD", "").strip() or "Admin@123"
        conn.execute(text(
            "INSERT INTO admins (username, password_hash, role, created_at) "
            "VALUES (:u, :p, 'super', :now)"
        ), {"u": "admin", "p": _hash_pwd(pwd), "now": datetime.now()})
