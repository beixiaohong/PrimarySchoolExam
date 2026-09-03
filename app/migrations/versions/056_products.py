"""056 - 商品与权益模板（S4-M1 / 07-技术实施方案 §3.2.4）

新建两张表（与 `app/models/commerce_product.py` 单一真相源一致，幂等建）：
- `products`：商城可售单元（会员/钻石/优惠券/组合包）；
- `product_benefits`：商品 → 多项可发放权益模板（下单时固化为 benefit_snapshot）。

均为全新表，无需 ALTER 补列。`create_all`（init_db）在本迁移前已建好表结构，
本迁移对已存在表为 no-op，仅对存量生产库补齐新表。
"""
import logging

from app.models.commerce_product import Product, ProductBenefit

logger = logging.getLogger("migrations")


def upgrade(db):
    Product.__table__.create(bind=db.get_bind(), checkfirst=True)
    ProductBenefit.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("056 商品与权益模板（products + product_benefits）已就绪")
    db.commit()
