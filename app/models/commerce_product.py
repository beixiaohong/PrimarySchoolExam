"""商品与权益模板模型（S4-M1 / 07-技术实施方案 §3.2.4 / 迁移 056）

商品中心数据底座：
- `products`：商城可售单元（会员/钻石/优惠券/组合包）；
- `product_benefits`：商品 → 多项可发放权益模板，下单时固化为订单的 `benefit_snapshot`。

设计要点：
- `description` 为 TEXT 列，**MySQL 不允许 DEFAULT**（07 §3.2.4 注），故 nullable=True 不配默认；
- `price_fen` / `original_fen` 整型「分」，禁止 Float（DB-01 铁律，S4 全局约定）；
- 本模型仅为存储结构，下单/支付逻辑在 `app/domains/commerce/services/order_service.py`
  与 `payment/*`（后续模块），本文件无外部调用。
"""
from datetime import datetime

from sqlalchemy import (Column, DateTime, Index, Integer, String, Text,
                        UniqueConstraint)

from ..database import Base


class Product(Base):
    """商品：商城可售单元（07 §3.2.4）"""
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_product_sku"),
        Index("idx_product_status", "status", "sort_order"),
        {"comment": "商品表"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    sku = Column(String(64), nullable=False, comment="商品编码，全局唯一")
    name = Column(String(128), nullable=False, comment="商品名称")
    type = Column(String(32), nullable=False,
                  comment="类型 membership/diamond/coupon/bundle")
    subtitle = Column(String(255), nullable=False, default="", comment="副标题")
    description = Column(Text, nullable=True, comment="详情（TEXT 不可有 DEFAULT）")
    price_fen = Column(Integer, nullable=False, comment="售价（分）")
    original_fen = Column(Integer, nullable=False, comment="原价（分）")
    duration_days = Column(Integer, nullable=False, default=0,
                           comment="会员天数（membership 类型用）")
    grade_scope = Column(String(64), nullable=False, default="", comment="适用学段")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序")
    status = Column(String(16), nullable=False, default="offline",
                    comment="online/offline")
    online_at = Column(DateTime, nullable=True, comment="上架时间")
    offline_at = Column(DateTime, nullable=True, comment="下架时间")
    created_by = Column(String(64), nullable=False, default="", comment="创建人")
    updated_by = Column(String(64), nullable=False, default="", comment="更新人")
    created_at = Column(DateTime, nullable=False, default=datetime.now,
                        comment="创建时间")
    updated_at = Column(DateTime, nullable=True, comment="更新时间")

    def __repr__(self):
        return f"<Product {self.id} sku:{self.sku} {self.name}>"


class ProductBenefit(Base):
    """商品权益模板：一个商品对应多项可发放权益（07 §3.2.4）"""
    __tablename__ = "product_benefits"
    __table_args__ = (
        Index("idx_pb_product", "product_id"),
        {"comment": "商品权益模板"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    product_id = Column(Integer, nullable=False, comment="商品ID")
    benefit_type = Column(String(32), nullable=False,
                          comment="vip_days/diamond/coupon/ai_quota")
    benefit_key = Column(String(64), nullable=False, default="",
                         comment="coupon 类型 / ai_quota 场景等")
    amount = Column(Integer, nullable=False, comment="数量（天数/钻石数/次数）")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序")
    created_at = Column(DateTime, nullable=False, default=datetime.now,
                        comment="创建时间")

    def __repr__(self):
        return (f"<ProductBenefit {self.id} product:{self.product_id} "
                f"{self.benefit_type}:{self.amount}>")
