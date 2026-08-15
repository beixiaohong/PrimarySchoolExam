"""账本模块建表迁移

导入模型即把 10 张账本表注册到 Base.metadata；create_all 幂等，
重复执行不会改变已有表结构。导入模型时不连库（引擎为懒连接）。
"""
from app.database import Base, engine
from app.models.ledger import (
    Bill, Account, Location, Merchant, Person, Project, Category,
    NotificationLog, UserReportSettings, RecurringTransaction,
)


def upgrade(db):
    """建表迁移：幂等创建 10 张账本表（导入模型注册到 Base.metadata 后用 create_all）。"""
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Bill.__table__,
            Account.__table__,
            Location.__table__,
            Merchant.__table__,
            Person.__table__,
            Project.__table__,
            Category.__table__,
            NotificationLog.__table__,
            UserReportSettings.__table__,
            RecurringTransaction.__table__,
        ],
    )
