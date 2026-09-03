"""058 - 支付流水 / 核销证据（S4-M1 / 07-技术实施方案 §3.2.6）

新建 `pay_transactions` 表（与 `app/models/commerce_payment.py` 单一真相源一致，幂等建）。
资金安全核心：uq_pt_external(external_no) 防重复核销；每笔核销/审批/退款/冲正留痕。

全新表，无需 ALTER 补列。`create_all`（init_db）已建结构，本迁移对已存在表为 no-op。
"""
import logging

from app.models.commerce_payment import PayTransaction

logger = logging.getLogger("migrations")


def upgrade(db):
    PayTransaction.__table__.create(bind=db.get_bind(), checkfirst=True)
    logger.info("058 支付流水（pay_transactions）已就绪")
    db.commit()
