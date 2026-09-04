"""S4 履约服务测试（test_s4_fulfillment）

覆盖：
- 钻石到账
- VIP 首次开通
- VIP 叠加续期（未过期再买应在原到期日上累加）
- VIP 已过期从今起算
- 补签卡批量 5 张
- 重复履约幂等（第二次调用不双发）
- 履约失败订单保持 PAID
- regrant-benefit 端点权限校验

测试库商品数据靠 fixture 自建（conftest.py 每次 drop_all）。
"""
import json
import secrets
from datetime import datetime, timedelta

import pytest

from app.database import SessionLocal
from app.models.commerce_order import Order
from app.models.commerce_product import Product, ProductBenefit
from app.models.user import VipUser
from app.models.makeup_card import MakeupCard
from app.domains.commerce.services.fulfillment import fulfill_order


# ---------------------------------------------------------------------------
# 商品 fixture（conftest 每次 drop_all，必须自建）
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def diamond_product(db):
    p = db.query(Product).filter(Product.sku == "test_diamond_60").first()
    if not p:
        p = Product(sku="test_diamond_60", name="60钻石", type="diamond",
                    subtitle="60 钻石", price_fen=600, original_fen=600,
                    sort_order=1, status="online")
        db.add(p)
        db.flush()
        db.add(ProductBenefit(product_id=p.id, benefit_type="diamond",
                              benefit_key="diamond", amount=60))
        db.commit()
        db.refresh(p)
    return p


@pytest.fixture()
def vip_product(db):
    p = db.query(Product).filter(Product.sku == "test_vip_month").first()
    if not p:
        p = Product(sku="test_vip_month", name="会员月卡", type="membership",
                    subtitle="30天VIP", price_fen=1000, original_fen=1000,
                    duration_days=30, sort_order=2, status="online")
        db.add(p)
        db.flush()
        db.add(ProductBenefit(product_id=p.id, benefit_type="vip_days",
                              benefit_key="vip_30", amount=30))
        db.commit()
        db.refresh(p)
    return p


@pytest.fixture()
def makeup_product(db):
    p = db.query(Product).filter(Product.sku == "test_makeup_5").first()
    if not p:
        p = Product(sku="test_makeup_5", name="补签卡×5", type="coupon",
                    subtitle="5张补签卡", price_fen=500, original_fen=500,
                    sort_order=3, status="online")
        db.add(p)
        db.flush()
        db.add(ProductBenefit(product_id=p.id, benefit_type="coupon",
                              benefit_key="makeup_card", amount=5))
        db.commit()
        db.refresh(p)
    return p


def _make_order(db, user_id, product, benefits, status="PAID"):
    """创建测试订单（直接写 DB，跳过下单路由）"""
    snapshot = json.dumps(
        [{"benefit_type": b.benefit_type, "benefit_key": b.benefit_key,
          "amount": int(b.amount)} for b in benefits],
        ensure_ascii=False,
    )
    now = datetime.now()
    order_no = now.strftime("%Y%m%d%H%M%S") + secrets.token_hex(3)
    order = Order(
        order_no=order_no,
        user_id=user_id,
        product_id=product.id,
        product_sku=product.sku,
        product_name=product.name,
        amount_fen=int(product.price_fen or 0),
        benefit_snapshot=snapshot,
        idempotency_key=f"test_{secrets.token_hex(6)}",
        status=status,
        expire_at=now + timedelta(hours=24),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestFulfillDiamond:
    def test_diamond_grant(self, db, diamond_product):
        """钻石到账：履约后用户钻石余额增加"""
        from app.domains.commerce.services.diamond import get_balance
        uid = "test_fulfill_diamond_user"
        benefits = db.query(ProductBenefit).filter_by(product_id=diamond_product.id).all()
        order = _make_order(db, uid, diamond_product, benefits)

        before = get_balance(db, uid)
        result = fulfill_order(db, order)
        assert result["ok"] is True
        assert result["skipped"] is False

        after = get_balance(db, uid)
        assert after == before + 60.0

        db.refresh(order)
        assert order.status == "FULFILLED"
        assert order.fulfilled_at is not None


class TestFulfillVIP:
    def test_vip_first_time(self, db, vip_product):
        """VIP 首次开通：expire_at 从当前时间 + 30 天"""
        uid = "test_fulfill_vip_new"
        benefits = db.query(ProductBenefit).filter_by(product_id=vip_product.id).all()
        order = _make_order(db, uid, vip_product, benefits)

        result = fulfill_order(db, order)
        assert result["ok"] is True

        vip = db.query(VipUser).filter(VipUser.user_id == uid).first()
        assert vip is not None
        assert vip.expire_at is not None
        # 应在 now+29天 ~ now+31天 之间（容差 1 天）
        expected = datetime.now() + timedelta(days=30)
        assert abs((vip.expire_at - expected).total_seconds()) < 86400 * 2

    def test_vip_stacking(self, db, vip_product):
        """VIP 叠加续期：未过期再买应在原到期日上累加"""
        uid = "test_fulfill_vip_stack"
        # 先设一个已有的 VIP（30 天后到期）
        future = datetime.now() + timedelta(days=30)
        db.add(VipUser(user_id=uid, note="existing", expire_at=future))
        db.commit()

        benefits = db.query(ProductBenefit).filter_by(product_id=vip_product.id).all()
        order = _make_order(db, uid, vip_product, benefits)
        result = fulfill_order(db, order)
        assert result["ok"] is True

        vip = db.query(VipUser).filter(VipUser.user_id == uid).first()
        # 应在原到期日 + 30 天 ≈ 60 天后
        expected = future + timedelta(days=30)
        assert abs((vip.expire_at - expected).total_seconds()) < 86400 * 2

    def test_vip_expired_from_now(self, db, vip_product):
        """VIP 已过期从今起算"""
        uid = "test_fulfill_vip_expired"
        past = datetime.now() - timedelta(days=10)
        db.add(VipUser(user_id=uid, note="expired", expire_at=past))
        db.commit()

        benefits = db.query(ProductBenefit).filter_by(product_id=vip_product.id).all()
        order = _make_order(db, uid, vip_product, benefits)
        result = fulfill_order(db, order)
        assert result["ok"] is True

        vip = db.query(VipUser).filter(VipUser.user_id == uid).first()
        # 已过期 → 从今起算 30 天
        expected = datetime.now() + timedelta(days=30)
        assert abs((vip.expire_at - expected).total_seconds()) < 86400 * 2


class TestFulfillMakeupCards:
    def test_batch_5_cards(self, db, makeup_product):
        """补签卡批量 5 张"""
        uid = "test_fulfill_makeup"
        benefits = db.query(ProductBenefit).filter_by(product_id=makeup_product.id).all()
        order = _make_order(db, uid, makeup_product, benefits)

        result = fulfill_order(db, order)
        assert result["ok"] is True

        card = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
        assert card is not None
        assert card.balance == 5
        assert card.total_earned == 5


class TestIdempotent:
    def test_double_fulfill_no_double_grant(self, db, diamond_product):
        """重复履约幂等：第二次调用不双发"""
        from app.domains.commerce.services.diamond import get_balance
        uid = "test_fulfill_idempotent"
        benefits = db.query(ProductBenefit).filter_by(product_id=diamond_product.id).all()
        order = _make_order(db, uid, diamond_product, benefits)

        result1 = fulfill_order(db, order)
        assert result1["ok"] is True
        bal1 = get_balance(db, uid)

        db.refresh(order)
        result2 = fulfill_order(db, order)
        assert result2["ok"] is True
        assert result2["skipped"] is True

        bal2 = get_balance(db, uid)
        assert bal2 == bal1  # 余额不变


class TestFulfillFailure:
    def test_failure_keeps_paid(self, db, monkeypatch):
        """履约失败订单保持 PAID"""
        uid = "test_fulfill_fail"
        p = Product(sku="test_fail", name="fail", type="diamond",
                    subtitle="", price_fen=100, original_fen=100,
                    sort_order=0, status="online")
        db.add(p)
        db.flush()
        db.add(ProductBenefit(product_id=p.id, benefit_type="diamond",
                              benefit_key="diamond", amount=10))
        db.commit()
        db.refresh(p)
        benefits = db.query(ProductBenefit).filter_by(product_id=p.id).all()
        order = _make_order(db, uid, p, benefits)

        # 模拟钻石发放失败
        import app.domains.commerce.services.fulfillment as ful
        monkeypatch.setattr(ful, "_fulfill_diamond", lambda *a, **k: (_ for _ in ()).throw(Exception("mock fail")))

        result = fulfill_order(db, order)
        assert result["ok"] is False
        assert "mock" in result["error"].lower() or "发放失败" in result["error"]

        db.refresh(order)
        assert order.status == "PAID"  # 保持 PAID，不关单


class TestRegrantEndpoint:
    def test_regrant_requires_auth(self, client):
        """regrant-benefit 端点需要管理员权限"""
        resp = client.post("/api/admin/commerce/orders/99999/regrant-benefit")
        assert resp.status_code in (401, 403)
