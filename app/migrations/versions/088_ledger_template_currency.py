"""账本模块 M4：记账模板 + 多币种

- 新建 db_ledger_tx_templates 表（一键复用记账模板）；
- db_ledger_accounts 增加 currency / rate_to_base / due_day 三列（多币种 + 信用卡还款日）；
- db_ledger_bills 增加 currency / rate_to_base / amount_orig 三列（多币种折算痕迹）。

幂等：表已存在时 create_all 无副作用；列存在性先查 information_schema，避免重复执行报错。
"""
from sqlalchemy import text

from app.database import Base, engine
from app.models.ledger import LedgerTxTemplate


def _column_exists(db, table, column):
    row = db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()
    return row is not None


def upgrade(db):
    """M4 模板 + 多币种：建表 + 账户/账单加币种与还款日字段。"""
    # 1) 建模板表
    Base.metadata.create_all(bind=engine, tables=[LedgerTxTemplate.__table__])

    # 2) 账户表加币种/汇率/还款日
    for col in ("currency", "rate_to_base", "due_day"):
        if not _column_exists(db, "db_ledger_accounts", col):
            if col == "due_day":
                db.execute(text("ALTER TABLE db_ledger_accounts ADD COLUMN due_day INT NULL"))
            elif col == "currency":
                db.execute(text("ALTER TABLE db_ledger_accounts ADD COLUMN currency VARCHAR(10) NULL"))
            else:
                db.execute(text("ALTER TABLE db_ledger_accounts ADD COLUMN rate_to_base DECIMAL(15,6) NULL"))

    # 3) 账单表加币种/汇率/原币金额
    for col in ("currency", "rate_to_base", "amount_orig"):
        if not _column_exists(db, "db_ledger_bills", col):
            if col == "currency":
                db.execute(text("ALTER TABLE db_ledger_bills ADD COLUMN currency VARCHAR(10) NULL"))
            elif col == "amount_orig":
                db.execute(text("ALTER TABLE db_ledger_bills ADD COLUMN amount_orig DECIMAL(15,2) NULL"))
            else:
                db.execute(text("ALTER TABLE db_ledger_bills ADD COLUMN rate_to_base DECIMAL(15,6) NULL"))

    db.commit()
