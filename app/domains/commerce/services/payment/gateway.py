"""支付网关抽象（S4-M2 / 07 §5.2.1 / D6）

业务层只依赖 `PaymentGateway` 协议，不感知具体实现。未来接入微信/支付宝时
新增同协议实现并在 `factory.py` 注册，订单/权益服务代码不变（AC-M0-2-12）。

传输结构均为纯数据（dataclass），便于跨层传递与单测。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class PaymentIntent:
    """创建支付意图的返回：用户侧看到的支付信息。"""
    qr_url: str
    memo: str
    amount_fen: int
    expire_at: Optional[datetime]
    tips: str = ""


@dataclass
class PaymentStatus:
    """查询支付状态返回。"""
    paid: bool
    status: str
    detail: str = ""


@dataclass
class ConfirmPayload:
    """人工核销确认载荷（后台 confirm-payment 提交）。"""
    external_no: str                       # 外部流水号（唯一，防重复核销）
    received_fen: int = 0                  # 实收金额（分）
    channel: str = ""                      # 收款渠道（微信/支付宝/银行卡）
    evidence_url: str = ""                 # 凭证截图 URL
    evidence_hash: str = ""                # 凭证文件哈希，防篡改
    operator_id: Optional[int] = None      # 操作人（admins.id）
    operator_name: str = ""
    ip: str = ""
    user_agent: str = ""
    remark: str = ""


@dataclass
class ConfirmResult:
    """核销确认结果（实际写库/状态机由 order_service 驱动）。"""
    ok: bool
    message: str = ""
    tx_id: Optional[int] = None            # 由 order_service 填充 pay_transactions.id


@dataclass
class RefundResult:
    """退款结果。"""
    ok: bool
    message: str = ""


class PaymentGateway(Protocol):
    """支付网关抽象：业务层唯一依赖的接口。"""

    def create_payment(self, order) -> PaymentIntent:
        """创建支付意图：返回用户侧支付信息（二维码/备注/金额/超时）。"""
        ...

    def query_payment(self, order) -> PaymentStatus:
        """查询支付状态（人工网关直接映射订单状态）。"""
        ...

    def confirm(self, order, payload: ConfirmPayload) -> ConfirmResult:
        """确认支付（人工网关：校验核销清单；自动网关：校验回调/查单）。"""
        ...

    def refund(self, order, amount_fen: int) -> RefundResult:
        """发起退款（自动网关调通道；人工网关交由后台审批）。"""
        ...
