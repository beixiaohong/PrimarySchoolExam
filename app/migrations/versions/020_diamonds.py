"""添加钻石系统：diamond_accounts + diamond_ledger 表"""
from sqlalchemy import text


def upgrade(db):
    # 创建 diamond_accounts 表
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS diamond_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(64) NOT NULL UNIQUE,
            balance FLOAT DEFAULT 0.0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    # 创建 diamond_ledger 表
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS diamond_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(64) NOT NULL,
            amount FLOAT NOT NULL,
            balance_after FLOAT NOT NULL,
            reason VARCHAR(50) DEFAULT '',
            ref_id INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_diamond_ledger_user_id ON diamond_ledger(user_id)"))

    # 为所有现有用户赠送 100 万钻石
    db.execute(text("""
        INSERT OR IGNORE INTO diamond_accounts (user_id, balance, updated_at)
        SELECT user_id, 1000000.0, datetime('now')
        FROM users
    """))
    # 记录赠送明细
    db.execute(text("""
        INSERT INTO diamond_ledger (user_id, amount, balance_after, reason, created_at)
        SELECT user_id, 1000000.0, 1000000.0, 'existing_user_grant', datetime('now')
        FROM users
        WHERE user_id NOT IN (SELECT user_id FROM diamond_ledger WHERE reason = 'existing_user_grant')
    """))
    db.commit()


def downgrade(db):
    pass  # 不删表，保持向前兼容
