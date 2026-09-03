"""S4-M2 验证：人工支付网关抽象（07 §5.2.1 / D6）

覆盖：
- PaymentGateway 协议结构齐备（gateway.py 传输结构）；
- ManualGateway.create_payment：返回收款码(env PAYMENT_QR_URL) + 付款备注(订单号后6位) + 金额 + 超时；
- ManualGateway.query_payment：映射订单状态 → paid/unpaid；
- ManualGateway.confirm：BR-M0-2-05 网关层校验（流水号/实收>0/金额一致），不写库；
- factory.get_gateway：默认 manual；未知网关名回退 manual（AC-M0-2-12 换实现零改动基础）；
- commerce.contracts.PaymentService 收口可用（跨域契约入口）。

🔴 持连铁律：网关/工厂无任何 DB/外部调用，纯校验与配置读取。
"""
import os

from app.domains.commerce.contracts import PaymentService
from app.domains.commerce.services.payment.factory import get_gateway, register_gateway
from app.domains.commerce.services.payment.gateway import (
    ConfirmPayload, PaymentGateway, PaymentIntent, PaymentStatus)
from app.domains.commerce.services.payment.manual_gateway import ManualGateway
from app.models.commerce_order import Order


def _make_order(order_no="S4M20001", amount_fen=3000, status="PENDING_PAYMENT"):
    o = Order(order_no=order_no, user_id="s4m2_u", product_id=1,
              amount_fen=amount_fen, idempotency_key="idem_m2",
              expire_at=__import__("datetime").datetime(2026, 9, 20, 0, 0))
    o.status = status
    return o


def test_s4_m2_gateway_structures(client):
    # 协议与传输结构可导入即用（契约入口经过 commerce.contracts 也有）
    assert PaymentGateway is not None
    assert PaymentIntent is not None and PaymentStatus is not None
    assert ConfirmPayload is not None


def test_s4_m2_create_payment(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_QR_URL", "https://qr.example.com/x.png")
    o = _make_order()
    intent = ManualGateway().create_payment(o)
    assert isinstance(intent, PaymentIntent)
    assert intent.qr_url == "https://qr.example.com/x.png"
    assert intent.memo == "S4M20001"[-6:] == "M20001"
    assert intent.amount_fen == 3000
    assert intent.expire_at is not None
    assert "订单号后 6 位" in intent.tips


def test_s4_m2_query_payment(client):
    unpaid = ManualGateway().query_payment(_make_order(status="PENDING_PAYMENT"))
    assert isinstance(unpaid, PaymentStatus)
    assert unpaid.paid is False
    assert unpaid.status == "PENDING_PAYMENT"

    paid = ManualGateway().query_payment(_make_order(status="PAID"))
    assert paid.paid is True
    fulfilled = ManualGateway().query_payment(_make_order(status="FULFILLED"))
    assert fulfilled.paid is True


def test_s4_m2_confirm_validation(client):
    o = _make_order(amount_fen=3000)
    gw = ManualGateway()

    # 缺外部流水号
    r1 = gw.confirm(o, ConfirmPayload(external_no="", received_fen=3000))
    assert r1.ok is False and "external_no" in r1.message

    # 实收为 0
    r2 = gw.confirm(o, ConfirmPayload(external_no="ext_1", received_fen=0))
    assert r2.ok is False and "大于 0" in r2.message

    # 金额不一致
    r3 = gw.confirm(o, ConfirmPayload(external_no="ext_1", received_fen=2999))
    assert r3.ok is False and "不一致" in r3.message

    # 通过
    r4 = gw.confirm(o, ConfirmPayload(external_no="ext_1", received_fen=3000,
                                       channel="wechat", operator_name="op1"))
    assert r4.ok is True


def test_s4_m2_refund_manual_pending(client):
    o = _make_order()
    r = ManualGateway().refund(o, 3000)
    assert r.ok is False and "后台审批" in r.message


def test_s4_m2_factory_default_and_fallback(client, monkeypatch):
    monkeypatch.delenv("PAYMENT_GATEWAY", raising=False)
    assert isinstance(get_gateway(), ManualGateway)

    # 未知网关名回退 manual（保证主链路不中断）
    monkeypatch.setenv("PAYMENT_GATEWAY", "wechat")
    assert isinstance(get_gateway(), ManualGateway)

    # 注册新网关后可被选中（AC-M0-2-12 验收基础）
    class FakeGateway(ManualGateway):
        pass
    register_gateway("fake", FakeGateway)
    monkeypatch.setenv("PAYMENT_GATEWAY", "fake")
    assert isinstance(get_gateway(), FakeGateway)
    # 复原，避免影响其它用例
    monkeypatch.setenv("PAYMENT_GATEWAY", "manual")
    register_gateway("wechat", ManualGateway)  # 占位抵消，保持 _GATEWAYS 稳定


def test_s4_m2_contract_surface(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_QR_URL", "https://qr.example.com/x.png")
    o = _make_order()
    # PaymentService 收口：create_payment / query_payment / confirm 均可经契约调用
    intent = PaymentService.create_payment(o)
    assert intent.amount_fen == 3000
    status = PaymentService.query_payment(o)
    assert status.paid is False
    res = PaymentService.confirm(o, ConfirmPayload(external_no="ext_1", received_fen=3000))
    assert res.ok is True
    refund = PaymentService.refund(o, 3000)
    assert refund.ok is False
