"""S4-M5 验证：后台交易接口（07 §4.2 / D11）

覆盖：
- 商品 CRUD：list / create（含 sku 唯一约束）/ update / status（上下架）
- 订单列表（多条件筛选）+ 详情（含 PayTransaction + AdminOperationLog）
- 核销：BR-M0-2-05 网关校验 + 写 pay_transactions(核销证据) + 写审计
- 核销金额不一致 → 网关拒（400）
- 大额审批通过（PENDING_APPROVAL → PAID）
- BR-M0-2-04：审批人=核销人 → 403
- 大额审批驳回（PENDING_APPROVAL → PENDING_PAYMENT）
- 退款（FULFILLED → REFUNDING）— 但本期没有 FULFILLED 转换流程，留为「非 FULFILLED → 400」
- 冲正（PAID → REVERSED）+ 写 REVERSE 流水
- 无 token → 401

铁律：路由纯 DB，无外部阻塞；全部 require_perm + _audit；订单/流水不可物理删除。
【注意】测试中跨 session 校验 DB 写入用 raw engine：
测试 session 在 fixture setup 时已开事务（snapshot 不含后续路由提交），
ORM session 的 expire_all() 无法跨事务快照刷新，因此验证路由写入必须用
独立的 raw engine.connect()，这是 SQLAlchemy + MySQL REPEATABLE READ 的已知行为。
"""
import pytest
from datetime import datetime

from app.database import SessionLocal
from app.models.commerce_order import Order
from app.models.commerce_payment import PayTransaction
from app.models.commerce_product import Product, ProductBenefit


ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def s4m5_seed():
    db = SessionLocal()
    sku_a = "s4m5_a"
    sku_b = "s4m5_b"
    for old in db.query(Product).filter(Product.sku.in_([sku_a, sku_b])).all():
        db.query(ProductBenefit).filter_by(product_id=old.id).delete()
        db.delete(old)
    db.commit()
    p_a = Product(sku=sku_a, name="S4M5商品A", type="membership",
                   price_fen=3000, original_fen=5000, duration_days=30,
                   status="online", sort_order=10)
    p_b = Product(sku=sku_b, name="S4M5商品B", type="diamond",
                   price_fen=1000, original_fen=1000, status="offline",
                   sort_order=0)
    db.add_all([p_a, p_b])
    db.commit()
    db.add(ProductBenefit(product_id=p_a.id, benefit_type="vip_days",
                          benefit_key="vip", amount=30))
    db.commit()
    db.refresh(p_a); db.refresh(p_b)
    yield {"p_a": p_a, "p_b": p_b}
    db = SessionLocal()
    for p in (p_a, p_b):
        order_ids = [o.id for o in db.query(Order).filter(
            Order.product_id == p.id).all()]
        if order_ids:
            db.query(PayTransaction).filter(
                PayTransaction.order_id.in_(order_ids)).delete(
                synchronize_session=False)
            db.query(Order).filter(Order.id.in_(order_ids)).delete(
                synchronize_session=False)
    db.commit()
    db.close()


@pytest.fixture
def _raw_db():
    """测试专用 raw engine fixture：跨 session 验证 DB 写入时使用。

    测试 session 在 fixture setup 时已开事务，ORM session 的 expire_all()
    无法跨事务快照刷新（MySQL REPEATABLE READ），所以路由提交的数据须用独立
    raw engine.connect() 读取。该 fixture 返回短生命周期的 raw engine。
    """
    from sqlalchemy import create_engine, text
    from app.config import DATABASE_URL
    eng = create_engine(DATABASE_URL)
    yield eng, text
    eng.dispose()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 商品 CRUD
# ---------------------------------------------------------------------------

def test_s4_m5_product_list(client, admin_token, s4m5_seed):
    r = client.get("/api/admin/commerce/products?status=online", headers=_h(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()
    skus = {it["sku"] for it in d["items"]}
    assert "s4m5_a" in skus
    assert "s4m5_b" not in skus


def test_s4_m5_product_create(client, admin_token, s4m5_seed):
    payload = {"sku": "s4m5_new", "name": "新商品", "type": "membership",
               "price_fen": 999, "original_fen": 1999, "duration_days": 7,
               "grade_scope": "1-3", "sort_order": 5, "subtitle": "体验卡",
               "description": "限时体验"}
    r = client.post("/api/admin/commerce/products", json=payload,
                    headers=_h(admin_token))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sku"] == "s4m5_new"
    assert d["status"] == "offline"  # 创建默认未上架
    # sku 重复 → 400
    r2 = client.post("/api/admin/commerce/products", json=payload,
                     headers=_h(admin_token))
    assert r2.status_code == 400


def test_s4_m5_product_update_and_status(client, admin_token, s4m5_seed):
    p = s4m5_seed["p_a"]
    # 更新
    upd = {"sku": p.sku, "name": "改名", "type": p.type, "price_fen": 3500,
           "original_fen": 6000, "duration_days": 30, "grade_scope": "1-6",
           "sort_order": 9, "subtitle": ""}
    r = client.put(f"/api/admin/commerce/products/{p.id}", json=upd,
                   headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "改名"
    assert r.json()["price_fen"] == 3500
    # 上下架
    rs = client.post(f"/api/admin/commerce/products/{p.id}/status",
                     json={"status": "offline"}, headers=_h(admin_token))
    assert rs.status_code == 200
    assert rs.json()["status"] == "offline"
    # 非法状态
    rs2 = client.post(f"/api/admin/commerce/products/{p.id}/status",
                      json={"status": "garbage"}, headers=_h(admin_token))
    assert rs2.status_code == 400


# ---------------------------------------------------------------------------
# 订单列表 / 详情
# ---------------------------------------------------------------------------

def _make_order(db, product, user="test_auth_uid", status="PENDING_PAYMENT",
                expire_in_h=24):
    """直接构造一个订单（绕开用户端 API，节省测试时间）。"""
    from app.domains.commerce.contracts import OrderService
    benefits = db.query(ProductBenefit).filter_by(product_id=product.id).all()
    o = OrderService.create_order(
        db, user_id=user, product=product, benefits=benefits,
        idempotency_key=f"seed_{int(datetime.now().timestamp()*1000)}_{product.id}")
    if status != "PENDING_PAYMENT":
        # 直接走 DB 修改（白盒）；仅测试用，不动状态机
        db.query(Order).filter_by(id=o.id).update({"status": status})
        db.commit()
        db.refresh(o)
    return o


def test_s4_m5_order_list_and_detail(client, admin_token, s4m5_seed):
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    o = _make_order(db, p)
    no = o.order_no
    # 列表
    r = client.get(f"/api/admin/commerce/orders?order_no={no}",
                  headers=_h(admin_token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(it["order_no"] == no for it in items)
    # 详情
    d = client.get(f"/api/admin/commerce/orders/{o.id}", headers=_h(admin_token))
    assert d.status_code == 200, d.text
    data = d.json()
    assert data["order_no"] == no
    assert "transactions" in data and "audit_logs" in data
    db.close()


# ---------------------------------------------------------------------------
# 核销
# ---------------------------------------------------------------------------

def test_s4_m5_confirm_payment(client, admin_token, s4m5_seed, _raw_db):
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    o = _make_order(db, p)
    r = client.post(f"/api/admin/commerce/orders/{o.id}/confirm-payment",
                    json={"external_no": "ext_s4m5_1", "received_fen": 3000,
                          "channel": "wechat", "evidence_url": "https://x/y.png"},
                    headers=_h(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PAID"
    # 写支付流水（raw engine 绕过 ORM session snapshot 隔离）
    raw_engine, text = _raw_db
    with raw_engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, order_id, action, external_no, amount_fen FROM pay_transactions "
            "WHERE order_id=:oid"), {"oid": o.id}).all()
        assert len(rows) >= 1, "pay_transactions 应有 CONFIRM 流水"
        row = dict(rows[0]._mapping)
        assert row["action"] == "CONFIRM"
        assert row["external_no"] == "ext_s4m5_1"
        assert row["amount_fen"] == 3000
        # 状态机内 _write_audit：admin='admin' / action='order:confirm_payment' / target_type='order'
        log_row = c.execute(text(
            "SELECT `admin` FROM admin_operation_logs WHERE target=:t AND action='order:confirm_payment' AND target_type='order'"),
            {"t": o.order_no}).first()
        assert log_row is not None
        assert log_row[0] == ADMIN_USER
    db.close()


def test_s4_m5_confirm_amount_mismatch_400(client, admin_token, s4m5_seed):
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    o = _make_order(db, p)
    r = client.post(f"/api/admin/commerce/orders/{o.id}/confirm-payment",
                    json={"external_no": "ext_x", "received_fen": 2999},
                    headers=_h(admin_token))
    assert r.status_code == 400
    db.close()


# ---------------------------------------------------------------------------
# 大额审批
# ---------------------------------------------------------------------------

def test_s4_m5_approve_separator_required(client, admin_token, s4m5_seed):
    """审批人 = 核销人 → 403（BR-M0-2-04）"""
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    o = _make_order(db, p, status="PENDING_APPROVAL")
    # 先以 admin 核销（注意：PENDING_APPROVAL 也允许 confirm_payment）
    rc = client.post(f"/api/admin/commerce/orders/{o.id}/confirm-payment",
                     json={"external_no": "ext_a", "received_fen": 3000},
                     headers=_h(admin_token))
    assert rc.status_code == 200
    # 此时订单已在 PAID；审批路由期望 PENDING_APPROVAL，会先被状态校验挡住
    # 为精确校验 BR-M0-2-04，先把订单改回 PENDING_APPROVAL，再以 admin 调 approve
    db.query(Order).filter_by(id=o.id).update({"status": "PENDING_APPROVAL"})
    db.commit()
    # 留下一条 CONFIRM 流水的 operator_name = admin.username
    ra = client.post(f"/api/admin/commerce/orders/{o.id}/approve",
                     headers=_h(admin_token))
    assert ra.status_code == 403, ra.text
    assert "审批人" in ra.text
    db.close()


def test_s4_m5_approve_ok_and_reject(client, admin_token, s4m5_seed):
    """审批通过 + 驳回（不同 admin 绕过 BR-M0-2-04）"""
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    # 准备 PENDING_APPROVAL 订单（白盒：先创建再改状态）
    o = _make_order(db, p)
    db.query(Order).filter_by(id=o.id).update({"status": "PENDING_APPROVAL"})
    db.commit()
    # 没有 CONFIRM 流水 → admin approve 直接通过（BR-M0-2-04 触发条件不满足）
    ra = client.post(f"/api/admin/commerce/orders/{o.id}/approve",
                     headers=_h(admin_token))
    assert ra.status_code == 200, ra.text
    assert ra.json()["status"] == "PAID"
    # 驳回：先创建另一单
    o2 = _make_order(db, p)
    db.query(Order).filter_by(id=o2.id).update({"status": "PENDING_APPROVAL"})
    db.commit()
    rj = client.post(f"/api/admin/commerce/orders/{o2.id}/reject",
                     headers=_h(admin_token))
    assert rj.status_code == 200
    assert rj.json()["status"] == "PENDING_PAYMENT"
    db.close()


# ---------------------------------------------------------------------------
# 退款
# ---------------------------------------------------------------------------

def test_s4_m5_refund_requires_fulfilled(client, admin_token, s4m5_seed):
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    o = _make_order(db, p)
    r = client.post(f"/api/admin/commerce/orders/{o.id}/refund",
                    json={"reason": "user request"}, headers=_h(admin_token))
    assert r.status_code == 400, r.text
    db.close()


# ---------------------------------------------------------------------------
# 冲正
# ---------------------------------------------------------------------------

def test_s4_m5_reverse_order(client, admin_token, s4m5_seed, _raw_db):
    db = SessionLocal()
    p = s4m5_seed["p_a"]
    o = _make_order(db, p)
    # 先核销到 PAID
    rc = client.post(f"/api/admin/commerce/orders/{o.id}/confirm-payment",
                     json={"external_no": "ext_rev", "received_fen": 3000},
                     headers=_h(admin_token))
    assert rc.status_code == 200
    # 冲正
    rr = client.post(f"/api/admin/commerce/orders/{o.id}/reverse",
                     json={"reason": "误单"}, headers=_h(admin_token))
    assert rr.status_code == 200, rr.text
    assert rr.json()["status"] == "REVERSED"
    # 写 REVERSE 流水（raw engine 绕过 ORM session snapshot 隔离）
    raw_engine, text = _raw_db
    with raw_engine.connect() as c:
        n = c.execute(text(
            "SELECT COUNT(*) FROM pay_transactions WHERE order_id=:oid AND action='REVERSE'"),
            {"oid": o.id}).scalar()
        assert n >= 1, "REVERSE 流水未写入"
    db.close()


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------

def test_s4_m5_no_token_401(client):
    r = client.get("/api/admin/commerce/products")
    assert r.status_code == 401