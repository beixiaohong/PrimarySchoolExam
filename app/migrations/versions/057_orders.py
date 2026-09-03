"""057 - 订单（S4-M1 / 07-技术实施方案 §3.2.5）

新建 `orders` 表（与 `app/models/commerce_order.py` 单一真相源一致，幂等建）。
状态机载体：PENDING_PAYMENT → ... → FULFILLED/REFUNDED/REVERSED；
含 uq_order_no / uq_order_idem 幂等索引与超时关单扫描索引。

全新表，无需 ALTER 补列。`create_all`（init_db）已建结构，本迁移对已存在表为 no-op。
"""
import logging

from app.models.commerce_order import Order

logger = logging.getLogger("migrations")


def upgrade(db):
    Order.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("057 订单（orders）已就绪")
    db.commit()
