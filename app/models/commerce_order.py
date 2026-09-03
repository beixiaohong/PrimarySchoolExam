"""订单模型（S4-M1 / 07-技术实施方案 §3.2.5 / 迁移 057）

订单状态机载体（07 §5.2.2 / ALLOWED_TRANSITIONS）：
PENDING_PAYMENT → PENDING_APPROVAL/PAID/CLOSED → ... → FULFILLED/REFUNDED/REVERSED。

设计要点：
- `amount_fen` 整型「分」（DB-01 铁律）；
- `benefit_snapshot` TEXT 固化下单时权益（商品改名不影响历史订单）；
- `uq_order_idem(user_id, idempotency_key)` 幂等兜底；空幂等键约定填 `nokey_<order_no>`（07 §3.2.5 注）；
- `idx_order_expire(status, expire_at)` 供超时关单扫描；
- 本模型仅存储结构，状态流转逻辑在 `app/domains/commerce/services/order_service.py`（后续模块）。
"""
from datetime import datetime

from sqlalchemy import (BigInteger, Column, DateTime, Index, Integer, String,
                        Text, UniqueConstraint)

from ..database import Base


class Order(Base):
    """订单：进入状态机的主链路单据（07 §3.2.5）"""
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_order_no"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_order_idem"),
        Index("idx_order_status", "status", "created_at"),
        Index("idx_order_user", "user_id", "created_at"),
        Index("idx_order_expire", "status", "expire_at"),
        {"comment": "订单表（状态机）"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键自增")
    order_no = Column(String(32), nullable=False, comment="业务订单号")
    user_id = Column(String(64), nullable=False, comment="用户ID")
    product_id = Column(Integer, nullable=False, comment="商品ID")
    product_sku = Column(String(64), nullable=False, default="", comment="冗余商品编码")
    product_name = Column(String(128), nullable=False, default="", comment="冗余商品名")
    amount_fen = Column(Integer, nullable=False, comment="应付金额（分）")
    benefit_snapshot = Column(Text, nullable=True, comment="JSON 权益快照（下单固化）")
    status = Column(String(24), nullable=False, default="PENDING_PAYMENT",
                    comment="PENDING_PAYMENT/PENDING_APPROVAL/PAID/FULFILLED/"
                            "CLOSED/REFUNDING/REFUNDED/REVERSED")
    idempotency_key = Column(String(64), nullable=False, default="", comment="幂等键")
    guardian_consent_at = Column(DateTime, nullable=True, comment="监护人同意时间")
    consent_rule_version = Column(String(32), nullable=False, default="",
                                  comment="同意规则版本")
    expire_at = Column(DateTime, nullable=False, comment="超时关单时间（创建+24h）")
    paid_at = Column(DateTime, nullable=True, comment="支付时间")
    fulfilled_at = Column(DateTime, nullable=True, comment="履约时间")
    closed_at = Column(DateTime, nullable=True, comment="关单时间")
    close_reason = Column(String(64), nullable=False, default="", comment="关单原因")
    client_ip = Column(String(64), nullable=False, default="", comment="客户端IP")
    user_agent = Column(String(255), nullable=False, default="", comment="UA")
    remark = Column(String(255), nullable=False, default="", comment="备注")
    created_at = Column(DateTime, nullable=False, default=datetime.now,
                        comment="创建时间")
    updated_at = Column(DateTime, nullable=True, comment="更新时间")

    def __repr__(self):
        return f"<Order {self.order_no} user:{self.user_id} {self.status}>"
