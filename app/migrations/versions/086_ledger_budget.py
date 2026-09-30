"""账本模块 M2：预算与超支提醒

- 新建 db_ledger_budgets 表（月/分类/项目预算，带预警阈值）；
- 为 db_ledger_notification_logs 增加 budget_id 列（可空，外键指向 db_ledger_budgets.id），
  使超支提醒可关联到具体预算。

幂等：表已存在时 create_all 无副作用；列/外键存在性先查 information_schema，避免重复执行报错。
"""
from sqlalchemy import text

from app.database import Base, engine
from app.models.ledger import LedgerBudget


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
    """M2 预算：建表 + 通知表加 budget_id 列与外键。"""
    # 1) 建预算表
    Base.metadata.create_all(bind=engine, tables=[LedgerBudget.__table__])

    # 2) 通知表增加 budget_id 列 + 外键
    if not _column_exists(db, "db_ledger_notification_logs", "budget_id"):
        db.execute(text("ALTER TABLE db_ledger_notification_logs ADD COLUMN budget_id INT NULL"))
    if not _fk_exists(db, "db_ledger_notification_logs", "fk_notification_budget"):
        db.execute(text(
            "ALTER TABLE db_ledger_notification_logs ADD CONSTRAINT fk_notification_budget "
            "FOREIGN KEY (budget_id) REFERENCES db_ledger_budgets (id)"
        ))
    db.commit()
