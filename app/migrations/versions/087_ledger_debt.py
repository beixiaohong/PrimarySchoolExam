"""账本模块 M3：借贷 + 退款/附件

- 新建 db_ledger_debts 表（债权/债务追踪）；
- 为 db_ledger_bills 增加 refund_of_id（退款关联原支出，自引用外键）与 attachment_url
  （票据附件）两列。

幂等：表已存在时 create_all 无副作用；列/外键存在性先查 information_schema，避免重复执行报错。
"""
from sqlalchemy import text

from app.database import Base, engine
from app.models.ledger import LedgerDebt


def _column_exists(db, table, column):
    row = db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).first()
    return row is not None


def _fk_exists(db, table, fk_name):
    row = db.execute(text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE table_schema = DATABASE() AND table_name = :t AND constraint_name = :n"
    ), {"t": table, "n": fk_name}).first()
    return row is not None


def upgrade(db):
    """M3 借贷：建表 + 账单表加退款/附件列与外键。"""
    # 1) 建借贷表
    Base.metadata.create_all(bind=engine, tables=[LedgerDebt.__table__])

    # 2) 账单表加 refund_of_id 与 attachment_url
    if not _column_exists(db, "db_ledger_bills", "refund_of_id"):
        db.execute(text("ALTER TABLE db_ledger_bills ADD COLUMN refund_of_id INT NULL"))
    if not _fk_exists(db, "db_ledger_bills", "fk_bills_refund_of"):
        db.execute(text(
            "ALTER TABLE db_ledger_bills ADD CONSTRAINT fk_bills_refund_of "
            "FOREIGN KEY (refund_of_id) REFERENCES db_ledger_bills (id)"
        ))
    if not _column_exists(db, "db_ledger_bills", "attachment_url"):
        db.execute(text("ALTER TABLE db_ledger_bills ADD COLUMN attachment_url VARCHAR(500) NULL"))

    db.commit()
