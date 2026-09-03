"""支付流水 / 核销证据模型（S4-M1 / 07-技术实施方案 §3.2.6 / 迁移 058）

资金安全核心载体：每笔核销/审批/退款/冲正留痕，供对账与防重复核销。

设计要点：
- `uq_pt_external(external_no)` 是**资金安全核心约束**：一笔实际收款只能核销一次；
  无外部流水号时约定填 `manual_<tx_id>`（07 §3.2.6 注，避免空串撞唯一索引）；
- `received_fen` 人工核销填写的实收金额，与 `amount_fen`（订单应付）分离，便于差异核对；
- `operator_id`/`approver_id` 关联 `admins.id`，大额审批与核销人可分离（BR-M0-2-04）；
- 本模型仅存储结构，核销逻辑在 `app/domains/commerce/services/payment/*`
  + `order_service.confirm`（后续模块）。
"""
from datetime import datetime

from sqlalchemy import (BigInteger, Column, DateTime, Index, Integer, String,
                        UniqueConstraint)

from ..database import Base


class PayTransaction(Base):
    """支付流水：每笔核销/审批/退款/冲正留痕（07 §3.2.6）"""
    __tablename__ = "pay_transactions"
    __table_args__ = (
        UniqueConstraint("external_no", name="uq_pt_external"),
        Index("idx_pt_order", "order_id"),
        Index("idx_pt_operator", "operator_id", "created_at"),
        {"comment": "支付流水/核销证据"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键自增")
    order_id = Column(BigInteger, nullable=False, comment="订单ID")
    order_no = Column(String(32), nullable=False, comment="订单号")
    gateway = Column(String(32), nullable=False, default="manual",
                    comment="manual/wechat/alipay")
    action = Column(String(24), nullable=False,
                    comment="CONFIRM/APPROVE/REFUND/REVERSE")
    amount_fen = Column(Integer, nullable=False, comment="本次操作金额（分）")
    received_fen = Column(Integer, nullable=False, default=0,
                          comment="实收金额（人工核销填写）")
    external_no = Column(String(128), nullable=False, default="",
                         comment="外部流水号（人工核销填写，唯一）")
    channel = Column(String(32), nullable=False, default="", comment="收款渠道")
    evidence_url = Column(String(512), nullable=False, default="", comment="凭证截图URL")
    evidence_hash = Column(String(64), nullable=False, default="", comment="凭证文件哈希")
    operator_id = Column(Integer, nullable=True, comment="操作人（admins.id）")
    operator_name = Column(String(64), nullable=False, default="", comment="操作人姓名")
    approver_id = Column(Integer, nullable=True, comment="审批人")
    approver_name = Column(String(64), nullable=False, default="", comment="审批人姓名")
    ip = Column(String(64), nullable=False, default="", comment="操作IP")
    user_agent = Column(String(255), nullable=False, default="", comment="UA")
    reason = Column(String(255), nullable=False, default="",
                    comment="退款/冲正/驳回原因")
    status = Column(String(16), nullable=False, default="success",
                    comment="success/failed")
    created_at = Column(DateTime, nullable=False, default=datetime.now,
                        comment="创建时间")

    def __repr__(self):
        return (f"<PayTransaction {self.id} order:{self.order_no} "
                f"{self.action} {self.status}>")
