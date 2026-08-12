"""钻石模型：用户钻石余额 + 收支明细账本

钻石用于 AI 功能扣费（1 万 token = 1 钻石，保留 2 位小数）。
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Float, Text

from ..database import Base


class DiamondAccount(Base):
    """用户钻石余额（冗余字段，快速查询）"""
    __tablename__ = "diamond_accounts"
    __table_args__ = {"comment": "钻石余额：每用户一条，AI 功能扣费用，1万token=1钻石"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, unique=True, index=True,
                     comment="用户标识")
    balance = Column(Float, default=0.0, comment="当前余额（保留2位小数）")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<DiamondAccount user={self.user_id} balance={self.balance}>"


class DiamondLedger(Base):
    """钻石收支明细（双记账）"""
    __tablename__ = "diamond_ledger"
    __table_args__ = {"comment": "钻石收支明细：双记账，正=收入负=支出"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    amount = Column(Float, nullable=False, comment="变动数量（正=收入，负=支出）")
    balance_after = Column(Float, nullable=False, comment="变动后余额")
    # reason 取值：grant=系统赠送，ai_explain=AI 讲解扣费，ai_report=AI 周报扣费，
    #             ai_encourage=AI 鼓励扣费，admin_adjust=管理员手动调整
    reason = Column(String(50), default="", comment="原因：grant/ai_explain/ai_report/ai_encourage/admin_adjust")
    ref_id = Column(Integer, default=0, comment="关联记录ID（如 ai_usage_log.id）")
    created_at = Column(DateTime, default=datetime.now, comment="发生时间")

    def __repr__(self):
        return f"<DiamondLedger user={self.user_id} amount={self.amount} reason={self.reason}>"
