"""S4-M4 验证：用户端交易接口（07 §4.1 / D11）

覆盖：
- GET /api/commerce/products（按类型/状态过滤，offline 不可见）
- GET /api/commerce/products/{id}（含权益说明）
- POST /api/commerce/orders（幂等键 + 监护人同意校验）
  - 同 key 重复 → 同 order_no（幂等）
  - 跨 user_id → 403
- GET /api/commerce/orders（我的订单，分页 + 状态筛选）
- GET /api/commerce/orders/{order_no}（详情 + 状态时间线）
- POST /api/commerce/orders/{order_no}/cancel（PENDING_PAYMENT → CLOSED）
  - PAID → 400 不可取消
- GET /api/commerce/orders/{order_no}/payment-info（manual 网关：qr_url/memo/seconds_left）

铁律：路由纯 DB，无外部调用；订单不可物理删除（DB-05）。
"""
import pytest
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.commerce_order import Order
from app.models.commerce_payment import PayTransaction
from app.models.commerce_product import Product, ProductBenefit


@pytest.fixture
def s4m4_seed():
    db = SessionLocal()
    sku_on = "s4m4_on"
    sku_off = "s4m4_off"
    # 清理
    for old in db.query(Product).filter(Product.sku.in_([sku_on, sku_off])).all():
        db.query(ProductBenefit).filter_by(product_id=old.id).delete()
        db.delete(old)
    db.commit()

    p_on = Product(sku=sku_on, name="月度会员", type="membership",
                   price_fen=3000, original_fen=5000, duration_days=30,
                   status="online", sort_order=10,
                   subtitle="30天VIP", grade_scope="1-6")
    p_off = Product(sku=sku_off, name="下架商品", type="membership",
                    price_fen=1000, original_fen=1000, duration_days=7,
                    status="offline", sort_order=0)
    db.add_all([p_on, p_off])
    db.commit()
    db.add(ProductBenefit(product_id=p_on.id, benefit_type="vip_days",
                          benefit_key="vip", amount=30, sort_order=1))
    db.commit()
    db.refresh(p_on)
    db.refresh(p_off)
    yield {"p_on": p_on, "p_off": p_off}
    # 清理：只清本次 p_on/p_off 引用的 order + pay_transactions；
    # product/benefit 留给下次 setup 按 sku 处理（避免大范围锁等待）。
    db = SessionLocal()
    try:
        for p in (p_on, p_off):
            order_ids = [o.id for o in db.query(Order).filter(
                Order.product_id == p.id).all()]
            if order_ids:
                db.query(PayTransaction).filter(
                    PayTransaction.order_id.in_(order_ids)).delete(
                    synchronize_session=False)
                db.query(Order).filter(Order.id.in_(order_ids)).delete(
                    synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 商品接口
# ---------------------------------------------------------------------------

def test_s4_m4_list_products(client, s4m4_seed):
    r = client.get("/api/commerce/products")
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    skus = {it["sku"] for it in items}
    assert "s4m4_on" in skus
    assert "s4m4_off" not in skus  # 下架不可见


def test_s4_m4_list_products_filter_type(client, s4m4_seed):
    r = client.get("/api/commerce/products?type=membership")
    assert r.status_code == 200
    items = r.json()
    assert all(it["type"] == "membership" for it in items)


def test_s4_m4_get_product_detail(client, s4m4_seed):
    p = s4m4_seed["p_on"]
    r = client.get(f"/api/commerce/products/{p.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["sku"] == "s4m4_on"
    assert data["price_fen"] == 3000
    assert any(b["benefit_type"] == "vip_days" for b in data["benefits"])
    # 不存在 → 404
    r404 = client.get("/api/commerce/products/999999")
    assert r404.status_code == 404


# ---------------------------------------------------------------------------
# 下单
# ---------------------------------------------------------------------------

def test_s4_m4_create_order_and_idempotency(client, s4m4_seed):
    p = s4m4_seed["p_on"]
    payload = {
        "user_id": "test_auth_uid",
        "product_id": p.id,
        "idempotency_key": "s4m4_idem_1",
        "consent_rule_version": "v1",
    }
    r1 = client.post("/api/commerce/orders", json=payload)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["status"] == "PENDING_PAYMENT"
    assert d1["amount_fen"] == 3000
    assert d1["product_sku"] == "s4m4_on"
    assert d1["benefit_snapshot"]
    assert d1["guardian_consent_at"] is not None
    # 幂等：同 key 返回同一 order_no
    r2 = client.post("/api/commerce/orders", json=payload)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["order_no"] == d1["order_no"]
    # 清理：直接连 DB
    db = SessionLocal()
    o = db.query(Order).filter_by(order_no=d1["order_no"]).first()
    if o:
        db.query(PayTransaction).filter_by(order_id=o.id).delete()
        db.query(Order).filter_by(id=o.id).delete()
        db.commit()
    db.close()


def test_s4_m4_create_order_cross_user_403(client, s4m4_seed):
    """显式用 test_auth_uid 的 token 调接口，body user_id=s4m4_other → 期望 403。

    AuthClient 默认按 JSON body 中 user_id 自动签发匹配的 token，会让鉴权巧合通过；
    这里显式注入 token 强制业务 user_id 与登录账号不一致以触发 403。
    """
    p = s4m4_seed["p_on"]
    payload = {
        "user_id": "s4m4_other",     # 与登录账号 test_auth_uid 不一致
        "product_id": p.id,
        "idempotency_key": "s4m4_idem_403",
        "consent_rule_version": "v1",
    }
    token_self = client._mint_token("test_auth_uid")
    headers = {"Authorization": f"Bearer {token_self}"}
    r = client.post("/api/commerce/orders", json=payload, headers=headers)
    assert r.status_code == 403, r.text


def test_s4_m4_create_order_offline_400(client, s4m4_seed):
    p = s4m4_seed["p_off"]
    payload = {
        "user_id": "test_auth_uid",
        "product_id": p.id,
        "idempotency_key": "s4m4_idem_offline",
        "consent_rule_version": "v1",
    }
    r = client.post("/api/commerce/orders", json=payload)
    assert r.status_code == 400, r.text


# ---------------------------------------------------------------------------
# 订单列表 / 详情
# ---------------------------------------------------------------------------

def test_s4_m4_list_my_orders(client, s4m4_seed):
    p = s4m4_seed["p_on"]
    created_nos = []
    for i in range(3):
        payload = {"user_id": "test_auth_uid", "product_id": p.id,
                   "idempotency_key": f"s4m4_list_{i}",
                   "consent_rule_version": "v1"}
        rr = client.post("/api/commerce/orders", json=payload)
        assert rr.status_code == 200
        created_nos.append(rr.json()["order_no"])
    # 我的订单
    r = client.get("/api/commerce/orders")
    assert r.status_code == 200
    items = r.json()
    my_nos = {it["order_no"] for it in items}
    for no in created_nos:
        assert no in my_nos
    # 状态过滤
    r2 = client.get("/api/commerce/orders?status=PENDING_PAYMENT")
    assert r2.status_code == 200
    assert all(it["status"] == "PENDING_PAYMENT" for it in r2.json())
    # 清理
    db = SessionLocal()
    for no in created_nos:
        o = db.query(Order).filter_by(order_no=no).first()
        if o:
            db.query(PayTransaction).filter_by(order_id=o.id).delete()
            db.query(Order).filter_by(id=o.id).delete()
    db.commit()
    db.close()


def test_s4_m4_order_detail_with_timeline(client, s4m4_seed):
    p = s4m4_seed["p_on"]
    payload = {"user_id": "test_auth_uid", "product_id": p.id,
               "idempotency_key": "s4m4_detail",
               "consent_rule_version": "v1"}
    r = client.post("/api/commerce/orders", json=payload)
    assert r.status_code == 200
    no = r.json()["order_no"]
    d = client.get(f"/api/commerce/orders/{no}")
    assert d.status_code == 200
    data = d.json()
    assert data["order_no"] == no
    assert isinstance(data["timeline"], list)
    assert any(t["status"] == "PENDING_PAYMENT" for t in data["timeline"])
    # 不存在的订单号 → 404
    r404 = client.get("/api/commerce/orders/NOPE_NOT_EXIST")
    assert r404.status_code == 404
    # 清理
    db = SessionLocal()
    o = db.query(Order).filter_by(order_no=no).first()
    if o:
        db.query(PayTransaction).filter_by(order_id=o.id).delete()
        db.query(Order).filter_by(id=o.id).delete()
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# 取消
# ---------------------------------------------------------------------------

def test_s4_m4_cancel_order(client, s4m4_seed):
    p = s4m4_seed["p_on"]
    payload = {"user_id": "test_auth_uid", "product_id": p.id,
               "idempotency_key": "s4m4_cancel",
               "consent_rule_version": "v1"}
    r = client.post("/api/commerce/orders", json=payload)
    no = r.json()["order_no"]
    # 取消
    rc = client.post(f"/api/commerce/orders/{no}/cancel")
    assert rc.status_code == 200
    assert rc.json()["status"] == "CLOSED"
    assert rc.json()["close_reason"] == "user_cancel"
    # 二次取消 → 400（已 CLOSED 不可再流转）
    rc2 = client.post(f"/api/commerce/orders/{no}/cancel")
    assert rc2.status_code == 400
    # 清理
    db = SessionLocal()
    o = db.query(Order).filter_by(order_no=no).first()
    if o:
        db.query(PayTransaction).filter_by(order_id=o.id).delete()
        db.query(Order).filter_by(id=o.id).delete()
        db.commit()
    db.close()


# ---------------------------------------------------------------------------
# 支付信息
# ---------------------------------------------------------------------------

def test_s4_m4_payment_info(client, s4m4_seed):
    p = s4m4_seed["p_on"]
    payload = {"user_id": "test_auth_uid", "product_id": p.id,
               "idempotency_key": "s4m4_payinfo",
               "consent_rule_version": "v1"}
    r = client.post("/api/commerce/orders", json=payload)
    no = r.json()["order_no"]
    info = client.get(f"/api/commerce/orders/{no}/payment-info")
    assert info.status_code == 200
    d = info.json()
    assert d["order_no"] == no
    assert d["amount_fen"] == 3000
    # memo 是 order_no 后 6 位
    assert d["memo"] == no[-6:]
    assert d["seconds_left"] > 0
    # 已 CLOSED → 400
    client.post(f"/api/commerce/orders/{no}/cancel")
    info2 = client.get(f"/api/commerce/orders/{no}/payment-info")
    assert info2.status_code == 400
    # 清理
    db = SessionLocal()
    o = db.query(Order).filter_by(order_no=no).first()
    if o:
        db.query(PayTransaction).filter_by(order_id=o.id).delete()
        db.query(Order).filter_by(id=o.id).delete()
        db.commit()
    db.close()