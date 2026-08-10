"""026_user_auth：用户认证体系（users 加列 + auth_codes 表 + 存量回填）

方言兼容写法（SQLite/MySQL 都会执行）：
- 用 inspector 幂等加列，列定义按当前方言编译；
- auth_codes 用独立 MetaData + checkfirst 建表；
- 存量用户回填 auth_type='nickname'、nickname=user_id。
"""
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, MetaData, String, Table, inspect, text,
)

# users 表新增列：(列名, 类型)
USER_NEW_COLUMNS = [
    ("email", String(120)),
    ("phone", String(20)),
    ("password_hash", String(128)),
    ("nickname", String(64)),
    ("auth_type", String(10)),
    ("email_verified", Boolean()),
    ("phone_verified", Boolean()),
    ("city", String(50)),
]

# email/phone 唯一索引（允许多个 NULL）
UNIQUE_INDEXES = {
    "ix_users_email": "CREATE UNIQUE INDEX ix_users_email ON users (email)",
    "ix_users_phone": "CREATE UNIQUE INDEX ix_users_phone ON users (phone)",
}


def upgrade(db):
    conn = db.connection()
    insp = inspect(conn)

    # 1) users 幂等加列
    existing_cols = {c["name"] for c in insp.get_columns("users")}
    for name, coltype in USER_NEW_COLUMNS:
        if name not in existing_cols:
            ddl = coltype.compile(dialect=conn.dialect)
            conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))

    # 2) email/phone 唯一索引
    existing_idx = {ix["name"] for ix in insp.get_indexes("users")}
    for name, sql in UNIQUE_INDEXES.items():
        if name not in existing_idx:
            conn.execute(text(sql))

    # 3) auth_codes 表
    meta = MetaData()
    Table(
        "auth_codes", meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("purpose", String(20), nullable=False, comment="register/bind/reset"),
        Column("target", String(120), nullable=False, index=True),
        Column("code_hash", String(128), nullable=False),
        Column("expires_at", DateTime, nullable=False),
        Column("used", Boolean, nullable=False, default=False),
        Column("fail_count", Integer, nullable=False, default=0),
        Column("created_at", DateTime, nullable=False),
    )
    meta.create_all(bind=conn, checkfirst=True)

    # 4) 存量用户回填为昵称账号
    conn.execute(text(
        "UPDATE users SET auth_type='nickname', nickname=user_id "
        "WHERE auth_type IS NULL"
    ))
