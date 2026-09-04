"""S4-M3 验证：订单状态机与编排（07 §5.2.2 / D7）

覆盖：
- ALLOWED_TRANSITIONS 全路径可流转（DoD：状态机全路径有单测）；
- 非法流转（含终态）抛 OrderTransitionError；
- create_order：固化 benefit_snapshot(JSON) + 状态 PENDING_PAYMENT + 超时+24h + 幂等；
- confirm_payment（核销）：网关校验通过 → PAID + 写 pay_transactions(核销证据) + 写审计；
- confirm_payment 金额不一致 → 网关拒，抛 OrderTransitionError；
- cancel：PENDING_PAYMENT → CLOSED(user_cancel)；
- scan_expired_orders：过期 PENDING_PAYMENT → CLOSED(timeout)；
- 持连铁律：transition 单事务（状态+流水+审计一次提交），无外部调用。

🔴 并发安全：transition 用 SELECT..FOR UPDATE + UPDATE..WHERE status=? 受影响行数判定。
"""
import json
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.domains.commerce.contracts import OrderService, OrderTransitionError
from app.domains.commerce.services.payment.gateway import ConfirmPayload
from app.models.commerce_order import Order
from app.models.commerce_payment import PayTransaction
from app.models.commerce_product import Product, ProductBenefit
from app.models.admin import AdminOperationLog

from app.domains.commerce.services.order_service import ALLOWED_TRANSITIONS


def _seed_product(db, sku="s4m3_sku"):
    # 先清理同 sku 的 product（连带其 ProductBenefit），避免跨测试污染
    for old in db.query(Product).filter_by(sku=sku).all():
        db.query(ProductBenefit).filter_by(product_id=old.id).delete()
        db.delete(old)
    db.commit()
    p = Product(sku=sku, name="月度会员", type="membership",
                price_fen=3000, original_fen=5000, duration_days=30)
    db.add(p)
    db.commit()
    db.add(ProductBenefit(product_id=p.id, benefit_type="vip_days",
                          benefit_key="vip", amount=30))
    db.commit()
    return p


def _cleanup(db, order_no, sku="s4m3_sku"):
    o = db.query(Order).filter_by(order_no=order_no).first()
    if o:
        db.query(PayTransaction).filter_by(order_id=o.id).delete()
        db.query(AdminOperationLog).filter_by(target=order_no).delete()
        db.query(Order).filter_by(order_no=order_no).delete()
    for old in db.query(Product).filter_by(sku=sku).all():
        db.query(ProductBenefit).filter_by(product_id=old.id).delete()
        db.delete(old)
    db.commit()


def _short_status(s: str) -> str:
    """状态名缩写：order_no 列限 VARCHAR(32)。"""
    return {
        "PENDING_PAYMENT": "PP",
        "PENDING_APPROVAL": "PA",
        "PAID": "PD",
        "FULFILLED": "FL",
        "REFUNDING": "RF",
        "CLOSED": "CL",
        "REFUNDED": "RD",
        "REVERSED": "RV",
    }.get(s, s[:4])


def test_s4_m3_allowed_transitions(client):
    # 全路径：每条允许边都能流转成功
    db = SessionLocal()
    product = _seed_product(db)
    for from_status, tos in ALLOWED_TRANSITIONS.items():
        for to in tos:
            # 建新订单并直接置为 from_status（不走 transition，避免前置依赖）
            now = datetime.now()
            on = f"S4M3T{_short_status(from_status)}_{_short_status(to)}"
            idem = f"idem_{_short_status(from_status)}_{_short_status(to)}"
            o = Order(order_no=on, user_id="s4m3_u", product_id=product.id,
                      product_sku=product.sku, product_name=product.name,
                      amount_fen=3000, idempotency_key=idem,
                      expire_at=now + timedelta(hours=1), status=from_status)
            db.add(o)
            db.commit()
            db.refresh(o)
            got = OrderService.transition(db, o, to,
                                          operator_name="op_test" if to in ("PAID", "REFUNDING") else "")
            assert got.status == to, f"{from_status}->{to} 期望 {to} 实得 {got.status}"
            # 清理
            db.query(PayTransaction).filter_by(order_id=o.id).delete()
            db.query(AdminOperationLog).filter_by(target=o.order_no).delete()
            db.query(Order).filter_by(id=o.id).delete()
            db.commit()
    _seed_product(db)  # 触发清理（用同 sku 覆盖删除）
    db.close()


def test_s4_m3_illegal_transition(client):
    db = SessionLocal()
    product = _seed_product(db)
    now = datetime.now()
    o = Order(order_no="S4M3ILLEGAL", user_id="s4m3_u", product_id=product.id,
              product_sku=product.sku, product_name=product.name,
              amount_fen=3000, idempotency_key="idem_illegal",
              expire_at=now + timedelta(hours=1), status="PENDING_PAYMENT")
    db.add(o)
    db.commit()
    db.refresh(o)
    # PENDING_PAYMENT -> FULFILLED 非法
    try:
        OrderService.transition(db, o, "FULFILLED")
        raise AssertionError("非法流转未拦截")
    except OrderTransitionError:
        pass
    # 终态 CLOSED -> PAID 非法
    db.query(Order).filter_by(id=o.id).update({"status": "CLOSED"})
    db.commit()
    db.refresh(o)
    try:
        OrderService.transition(db, o, "PAID")
        raise AssertionError("终态流转未拦截")
    except OrderTransitionError:
        pass
    _cleanup(db, "S4M3ILLEGAL")
    db.close()


def test_s4_m3_create_order(client):
    db = SessionLocal()
    product = _seed_product(db)
    o = OrderService.create_order(db, user_id="s4m3_u", product=product,
                                  benefits=db.query(ProductBenefit).filter_by(product_id=product.id).all(),
                                  idempotency_key="idem_create")
    assert o.status == "PENDING_PAYMENT"
    snap = json.loads(o.benefit_snapshot)
    assert snap == [{"benefit_type": "vip_days", "benefit_key": "vip", "amount": 30}]
    assert o.expire_at >= datetime.now() + timedelta(hours=23)
    # 幂等：同 (user_id, idempotency_key) 返回既有订单
    o2 = OrderService.create_order(db, user_id="s4m3_u", product=product,
                                   benefits=[], idempotency_key="idem_create")
    assert o2.id == o.id
    _cleanup(db, o.order_no)
    db.close()


def test_s4_m3_confirm_payment(client):
    db = SessionLocal()
    product = _seed_product(db)
    o = OrderService.create_order(db, user_id="s4m3_u", product=product,
                                  benefits=db.query(ProductBenefit).filter_by(product_id=product.id).all(),
                                  idempotency_key="idem_confirm")
    # 核销：流水号 + 实收=应付 → 通过
    res = OrderService.confirm_payment(
        db, o, ConfirmPayload(external_no="ext_s4m3_1", received_fen=3000,
                              channel="wechat", operator_name="op1", ip="1.2.3.4"),
        operator_name="op1", ip="1.2.3.4")
    assert res.status == "PAID"
    assert res.paid_at is not None
    # 写支付流水（核销证据）
    tx = db.query(PayTransaction).filter_by(order_id=o.id).first()
    assert tx is not None and tx.action == "CONFIRM" and tx.external_no == "ext_s4m3_1"
    # 写审计
    log = db.query(AdminOperationLog).filter_by(target=o.order_no).first()
    assert log is not None and log.action == "order:confirm_payment"
    _cleanup(db, o.order_no)
    db.close()


def test_s4_m3_confirm_amount_mismatch(client):
    db = SessionLocal()
    product = _seed_product(db)
    o = OrderService.create_order(db, user_id="s4m3_u", product=product,
                                  benefits=[], idempotency_key="idem_mismatch")
    try:
        OrderService.confirm_payment(db, o, ConfirmPayload(external_no="ext_x", received_fen=2999))
        raise AssertionError("金额不一致未拦截")
    except OrderTransitionError as e:
        assert "不一致" in str(e)
    # 订单应保持 PENDING_PAYMENT（未污染）
    assert db.query(Order).filter_by(id=o.id).first().status == "PENDING_PAYMENT"
    _cleanup(db, o.order_no)
    db.close()


def test_s4_m3_cancel(client):
    db = SessionLocal()
    product = _seed_product(db)
    o = OrderService.create_order(db, user_id="s4m3_u", product=product,
                                  benefits=[], idempotency_key="idem_cancel")
    got = OrderService.cancel(db, o)
    assert got.status == "CLOSED"
    assert got.close_reason == "user_cancel"
    assert got.closed_at is not None
    _cleanup(db, o.order_no)
    db.close()


def test_s4_m3_scan_expired(client):
    db = SessionLocal()
    product = _seed_product(db)
    now = datetime.now()
    o = Order(order_no="S4M3EXP", user_id="s4m3_u", product_id=product.id,
              product_sku=product.sku, product_name=product.name,
              amount_fen=3000, idempotency_key="idem_exp",
              expire_at=now - timedelta(hours=1), status="PENDING_PAYMENT")
    db.add(o)
    db.commit()
    n = OrderService.scan_expired_orders(db, now=now)
    assert n >= 1
    got = db.query(Order).filter_by(order_no="S4M3EXP").first()
    assert got.status == "CLOSED"
    assert got.close_reason == "timeout"
    _cleanup(db, "S4M3EXP")
    db.close()
