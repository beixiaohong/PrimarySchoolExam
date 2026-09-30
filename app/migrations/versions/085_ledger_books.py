"""账本模块 M1：多账本支持（随手记式场景账本）

- 新建 db_ledger_books 表；
- 为 db_ledger_bills / db_ledger_accounts / db_ledger_recurring_transactions 增加
  book_id 列（可空，外键指向 db_ledger_books.id）；
- 存量数据回填：为每个已有账本数据的用户创建一本「日常账本」(is_default=1)，
  并将其 bills/accounts/recurring 的 book_id 指向该默认账本；
- 新用户由应用层 _ensure_default_book 懒创建默认账本。

幂等：列/外键存在性先查 information_schema，避免重复执行报错。
"""
from sqlalchemy import text

from app.database import Base, engine
from app.models.ledger import LedgerBook


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
    """M1 多账本：建表 + 加列 + 外键 + 存量回填默认账本。"""
    # 1) 建账本表
    Base.metadata.create_all(bind=engine, tables=[LedgerBook.__table__])

    targets = [
        ("db_ledger_bills", "fk_bills_book"),
        ("db_ledger_accounts", "fk_accounts_book"),
        ("db_ledger_recurring_transactions", "fk_recurring_book"),
    ]
    for table_name, fk_name in targets:
        if not _column_exists(db, table_name, "book_id"):
            db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN book_id INT NULL"))
        if not _fk_exists(db, table_name, fk_name):
            # InnoDB 会在外键列自动建索引；NULL 值不触发外键约束
            db.execute(text(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {fk_name} "
                f"FOREIGN KEY (book_id) REFERENCES db_ledger_books (id)"
            ))
    db.commit()

    # 2) 存量回填：为每个已有账本数据的用户建默认账本并挂接
    users = db.execute(text(
        "SELECT user_id FROM db_ledger_bills "
        "UNION SELECT user_id FROM db_ledger_accounts "
        "UNION SELECT user_id FROM db_ledger_recurring_transactions"
    )).fetchall()
    for (uid,) in users:
        existing = db.execute(text(
            "SELECT id FROM db_ledger_books WHERE user_id = :u AND is_default = 1"
        ), {"u": uid}).first()
        if existing:
            book_id = existing[0]
        else:
            db.execute(text(
                "INSERT INTO db_ledger_books (user_id, name, book_type, is_default, created_at) "
                "VALUES (:u, '日常账本', 'daily', 1, NOW())"
            ), {"u": uid})
            book_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        db.execute(text(
            "UPDATE db_ledger_bills SET book_id = :b WHERE user_id = :u AND book_id IS NULL"
        ), {"b": book_id, "u": uid})
        db.execute(text(
            "UPDATE db_ledger_accounts SET book_id = :b WHERE user_id = :u AND book_id IS NULL"
        ), {"b": book_id, "u": uid})
        db.execute(text(
            "UPDATE db_ledger_recurring_transactions SET book_id = :b WHERE user_id = :u AND book_id IS NULL"
        ), {"b": book_id, "u": uid})
    db.commit()
