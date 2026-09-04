"""人工支付网关（S4-M2 / 07 §5.2.1 / D6）

本期唯一实现：**不做任何外部调用**，核销结果以运营后台操作为准。

- `create_payment`：返回收款码（环境变量 PAYMENT_QR_URL）+ 付款备注（订单号后 6 位）；
- `query_payment`：直接映射订单状态（人工网关无外部查单）；
- `confirm`：纯校验核销清单（BR-M0-2-05 中网关可校验的部分：流水号唯一/实收>0/金额一致）；
  权限、订单状态、频次、凭证完整性由 `order_service`（M3）与后台 confirm-payment（M5）强制；
- `refund`：人工网关不直接退款，交由后台审批（见 M5/S6）。

🔴 持连铁律：本网关无任何 DB / 外部阻塞调用，纯计算与校验。
"""
import os

from app.config import (RECHARGE_WECHAT_QR, RECHARGE_ALIPAY_QR,
                        RECHARGE_CS_CONTACT)
from .gateway import (ConfirmPayload, ConfirmResult, PaymentIntent,
                      PaymentStatus, RefundResult)


class ManualGateway:
    """人工支付网关：核销以运营操作为准，无外部通道。"""

    def create_payment(self, order) -> PaymentIntent:
        # qr_url 优先取 PAYMENT_QR_URL 环境变量覆盖项，否则取微信收款码
        qr_url = os.environ.get("PAYMENT_QR_URL", "").strip() or RECHARGE_WECHAT_QR
        memo = (order.order_no or "")[-6:]
        return PaymentIntent(
            qr_url=qr_url,
            memo=memo,
            amount_fen=int(order.amount_fen or 0),
            expire_at=order.expire_at,
            tips="请务必在付款备注中填写订单号后 6 位",
            wechat_qr=RECHARGE_WECHAT_QR,
            alipay_qr=RECHARGE_ALIPAY_QR,
            cs_contact=RECHARGE_CS_CONTACT,
        )

    def query_payment(self, order) -> PaymentStatus:
        # 已支付/已履约/退款中/已退款 视为「已付」
        paid = order.status in ("PAID", "FULFILLED", "REFUNDING", "REFUNDED")
        return PaymentStatus(paid=paid, status=order.status)

    def confirm(self, order, payload: ConfirmPayload) -> ConfirmResult:
        """核销校验（网关层）：纯校验，不写库。

        校验清单 BR-M0-2-05 中网关可覆盖的项：
        - 外部流水号必须存在（对应 uq_pt_external 防重复核销）；
        - 实收金额必须为正；
        - 实收金额须与应付金额一致。
        其余（权限/状态/频次/凭证）由 order_service + 后台接口强制，不在网关内。
        """
        if not payload.external_no:
            return ConfirmResult(ok=False, message="缺少外部流水号 external_no（防重复核销约束）")
        if payload.received_fen <= 0:
            return ConfirmResult(ok=False, message="实收金额必须大于 0")
        if payload.received_fen != int(order.amount_fen or 0):
            return ConfirmResult(
                ok=False,
                message=f"实收金额({payload.received_fen})与应付金额({int(order.amount_fen or 0)})不一致",
            )
        return ConfirmResult(ok=True, message="核销校验通过")

    def refund(self, order, amount_fen: int) -> RefundResult:
        # 人工网关无自动退款通道，交由后台审批（见 M5/S6）
        return RefundResult(ok=False, message="人工网关退款须经后台审批（见 M5/S6）")
