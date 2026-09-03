"""S4-M1 验证：交易核心数据底座（迁移 056/057/058 + 模型，07 §3.2.4~§3.2.6）

覆盖：
- Product / ProductBenefit / Order / PayTransaction 模型层新列属性齐备；
- products 可插入/查询，唯一约束 uq_product_sku 生效；
- orders 可插入/查询，唯一约束 uq_order_no 与 uq_order_idem(user_id,idempotency_key) 生效；
- pay_transactions 可插入/查询，核心防重复核销约束 uq_pt_external 生效；
- 迁移 056/057/058 经 run_migrations 幂等应用（启动已跑，再次运行不重列）。

均为全新表，无默认值/存量数据约束；金额沿用整型「分」（DB-01）。
"""
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.commerce_product import Product, ProductBenefit
from app.models.commerce_order import Order
from app.models.commerce_payment import PayTransaction


def test_s4_m1_product_columns(client):
    for attr in (
        "sku", "name", "type", "subtitle", "description", "price_fen",
        "original_fen", "duration_days", "grade_scope", "sort_order",
        "status", "online_at", "offline_at", "created_by", "updated_by",
        "created_at", "updated_at",
    ):
        assert hasattr(Product, attr), f"Product 缺列 {attr}"
    for attr in ("product_id", "benefit_type", "benefit_key", "amount",
                 "sort_order", "created_at"):
        assert hasattr(ProductBenefit, attr), f"ProductBenefit 缺列 {attr}"


def test_s4_m1_order_columns(client):
    for attr in (
        "order_no", "user_id", "product_id", "product_sku", "product_name",
        "amount_fen", "benefit_snapshot", "status", "idempotency_key",
        "guardian_consent_at", "consent_rule_version", "expire_at",
        "paid_at", "fulfilled_at", "closed_at", "close_reason",
        "client_ip", "user_agent", "remark", "created_at", "updated_at",
    ):
        assert hasattr(Order, attr), f"Order 缺列 {attr}"


def test_s4_m1_pay_tx_columns(client):
    for attr in (
        "order_id", "order_no", "gateway", "action", "amount_fen",
        "received_fen", "external_no", "channel", "evidence_url",
        "evidence_hash", "operator_id", "operator_name", "approver_id",
        "approver_name", "ip", "user_agent", "reason", "status", "created_at",
    ):
        assert hasattr(PayTransaction, attr), f"PayTransaction 缺列 {attr}"


def test_s4_m1_product_crud(client):
    db = SessionLocal()
    db.query(Product).filter_by(sku="s4m1_sku_a").delete()
    db.commit()

    p = Product(sku="s4m1_sku_a", name="月度会员", type="membership",
                price_fen=3000, original_fen=5000, duration_days=30,
                grade_scope="1-9")
    db.add(p)
    db.commit()
    got = db.query(Product).filter_by(sku="s4m1_sku_a").first()
    assert got is not None
    assert got.name == "月度会员"
    assert got.price_fen == 3000
    assert got.duration_days == 30

    # 关联权益模板
    db.add(ProductBenefit(product_id=got.id, benefit_type="vip_days",
                          benefit_key="vip", amount=30))
    db.commit()
    pb = db.query(ProductBenefit).filter_by(product_id=got.id).first()
    assert pb is not None and pb.amount == 30

    # 唯一约束：同 sku 再插应抛 IntegrityError
    dup = Product(sku="s4m1_sku_a", name="冲突", type="diamond",
                  price_fen=100, original_fen=100)
    db.add(dup)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_product_sku 未生效")
    except IntegrityError:
        db.rollback()

    db.query(ProductBenefit).filter_by(product_id=got.id).delete()
    db.query(Product).filter_by(sku="s4m1_sku_a").delete()
    db.commit()
    db.close()


def test_s4_m1_order_crud(client):
    db = SessionLocal()
    db.query(Order).filter_by(order_no="S4M10001").delete()
    db.query(Order).filter_by(user_id="s4m1_u", idempotency_key="idem_x").delete()
    db.commit()

    o = Order(order_no="S4M10001", user_id="s4m1_u", product_id=1,
              product_sku="s4m1_sku_a", product_name="月度会员",
              amount_fen=3000, idempotency_key="idem_x",
              expire_at=datetime(2026, 9, 10, 0, 0))
    db.add(o)
    db.commit()
    got = db.query(Order).filter_by(order_no="S4M10001").first()
    assert got is not None
    assert got.status == "PENDING_PAYMENT"
    assert got.amount_fen == 3000

    # uq_order_no：同 order_no 再插应抛 IntegrityError
    dup_no = Order(order_no="S4M10001", user_id="s4m1_u", product_id=1,
                   amount_fen=3000, idempotency_key="idem_y",
                   expire_at=datetime(2026, 9, 10, 0, 0))
    db.add(dup_no)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_order_no 未生效")
    except IntegrityError:
        db.rollback()

    # uq_order_idem：同 (user_id, idempotency_key) 再插应抛 IntegrityError
    dup_idem = Order(order_no="S4M10002", user_id="s4m1_u",
                     product_id=1, amount_fen=3000,
                     idempotency_key="idem_x",
                     expire_at=datetime(2026, 9, 10, 0, 0))
    db.add(dup_idem)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_order_idem 未生效")
    except IntegrityError:
        db.rollback()

    db.query(Order).filter_by(order_no="S4M10001").delete()
    db.query(Order).filter_by(user_id="s4m1_u", idempotency_key="idem_x").delete()
    db.commit()
    db.close()


def test_s4_m1_pay_tx_crud(client):
    db = SessionLocal()
    db.query(PayTransaction).filter_by(order_no="S4M10001").delete()
    db.query(PayTransaction).filter_by(external_no="ext_s4m1_1").delete()
    db.commit()

    tx = PayTransaction(order_id=1, order_no="S4M10001", gateway="manual",
                        action="CONFIRM", amount_fen=3000,
                        received_fen=3000, external_no="ext_s4m1_1",
                        operator_name="op1")
    db.add(tx)
    db.commit()
    got = db.query(PayTransaction).filter_by(order_no="S4M10001").first()
    assert got is not None
    assert got.action == "CONFIRM"
    assert got.received_fen == 3000

    # 核心资金安全约束：同 external_no 再插应抛 IntegrityError（防重复核销）
    dup = PayTransaction(order_id=1, order_no="S4M10001", gateway="manual",
                         action="CONFIRM", amount_fen=3000,
                         external_no="ext_s4m1_1", operator_name="op2")
    db.add(dup)
    try:
        db.commit()
        raise AssertionError("唯一约束 uq_pt_external 未生效（资金安全约束）")
    except IntegrityError:
        db.rollback()

    db.query(PayTransaction).filter_by(order_no="S4M10001").delete()
    db.query(PayTransaction).filter_by(external_no="ext_s4m1_1").delete()
    db.commit()
    db.close()


def test_s4_m1_migration_idempotent(client):
    """迁移 056/057/058 已在 lifespan 启动时应用，再次 run_migrations 不重列（幂等）。"""
    from app.migrations.runner import run_migrations
    executed = run_migrations()
    assert isinstance(executed, list)
    assert "056_products" not in executed
    assert "057_orders" not in executed
    assert "058_payments" not in executed
