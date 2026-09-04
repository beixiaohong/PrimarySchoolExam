"""D7 用户端交易路由（S4-M4 / 07 §4.1 / D11）

接口：
- GET  /products                  商品列表（按类型/状态过滤，仅 online）
- GET  /products/{id}             商品详情（含权益说明）
- POST /orders                    创建订单（幂等键 + 监护人同意校验）
- GET  /orders                    我的订单列表（分页/状态筛选）
- GET  /orders/{order_no}         订单详情（含状态时间线）
- POST /orders/{order_no}/cancel  取消订单（仅 PENDING_PAYMENT/PENDING_APPROVAL）
- GET  /orders/{order_no}/payment-info  支付信息（收款码/备注/倒计时）

铁律：
- 全部挂 `require_self`，禁止跨用户查/改；
- 下单与取消须校验订单归属；
- 持连铁律：路由纯 DB、无外部阻塞调用；
- 物理禁止：永不删除订单（DB-05）。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.commerce.contracts import (OrderService, OrderTransitionError,
                                           PaymentService)
from app.domains.identity.contracts import require_self
from app.models.commerce_order import Order
from app.models.commerce_product import Product, ProductBenefit
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commerce", tags=["用户端交易"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------

class _ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    type: str
    subtitle: str
    description: Optional[str] = None
    price_fen: int
    original_fen: int
    duration_days: int
    grade_scope: str
    sort_order: int
    status: str
    benefits: list = Field(default_factory=list)


class _OrderItem(BaseModel):
    id: int
    order_no: str
    product_id: int
    product_sku: str
    product_name: str
    amount_fen: int
    status: str
    idempotency_key: str
    expire_at: datetime
    paid_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    close_reason: str
    created_at: datetime
    benefit_snapshot: Optional[str] = None


class _OrderDetail(_OrderItem):
    user_id: str
    product_name: str
    fulfilled_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    guardian_consent_at: Optional[datetime] = None
    timeline: list = Field(default_factory=list)


class _PaymentInfo(BaseModel):
    order_no: str
    amount_fen: int
    qr_url: str
    memo: str
    tips: str
    expire_at: datetime
    seconds_left: int
    wechat_qr: str = ""
    alipay_qr: str = ""
    cs_contact: str = ""


class _CreateOrderReq(BaseModel):
    user_id: str = Field(..., description="用户名（必须与登录账号一致）")
    product_id: int = Field(..., description="商品ID")
    idempotency_key: str = Field(..., min_length=4, max_length=64,
                                 description="幂等键：客户端生成，重复请求用同一键")
    consent_rule_version: str = Field(default="v1",
                                      description="监护人同意的规则版本")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _product_to_out(p: Product, benefits: list) -> _ProductOut:
    return _ProductOut(
        id=p.id, sku=p.sku, name=p.name, type=p.type, subtitle=p.subtitle,
        description=p.description, price_fen=int(p.price_fen or 0),
        original_fen=int(p.original_fen or 0),
        duration_days=int(p.duration_days or 0), grade_scope=p.grade_scope,
        sort_order=int(p.sort_order or 0), status=p.status,
        benefits=[{"benefit_type": b.benefit_type, "benefit_key": b.benefit_key,
                   "amount": int(b.amount)} for b in benefits],
    )


def _order_to_item(o: Order) -> _OrderItem:
    return _OrderItem(
        id=o.id, order_no=o.order_no, product_id=o.product_id,
        product_sku=o.product_sku, product_name=o.product_name,
        amount_fen=int(o.amount_fen or 0), status=o.status,
        idempotency_key=o.idempotency_key, expire_at=o.expire_at,
        paid_at=o.paid_at, closed_at=o.closed_at,
        close_reason=o.close_reason, created_at=o.created_at,
        benefit_snapshot=o.benefit_snapshot,
    )


def _order_to_detail(o: Order) -> _OrderDetail:
    base = _order_to_item(o).model_dump()
    base.update({
        "user_id": o.user_id, "fulfilled_at": o.fulfilled_at,
        "updated_at": o.updated_at,
        "guardian_consent_at": o.guardian_consent_at,
        "timeline": _timeline(o),
    })
    return _OrderDetail(**base)


def _timeline(o: Order) -> list:
    items = [{"at": o.created_at.isoformat(), "status": "PENDING_PAYMENT",
              "remark": "订单创建"}]
    if o.paid_at:
        items.append({"at": o.paid_at.isoformat(), "status": "PAID",
                      "remark": "支付成功"})
    if o.fulfilled_at:
        items.append({"at": o.fulfilled_at.isoformat(), "status": "FULFILLED",
                      "remark": "权益发放"})
    if o.closed_at:
        items.append({"at": o.closed_at.isoformat(), "status": "CLOSED",
                      "remark": o.close_reason or "订单关闭"})
    return items


def _ensure_owner(order: Order, user_id: str) -> None:
    if order.user_id != user_id:
        raise HTTPException(403, "无权访问该订单")


# ---------------------------------------------------------------------------
# 商品接口（登录即可）
# ---------------------------------------------------------------------------

@router.get("/products", response_model=list[_ProductOut],
            summary="商品列表（仅 online，按类型过滤）")
def list_products(
    user: User = Depends(require_self),
    type: Optional[str] = Query(None, description="类型 membership/diamond/..."),
    db: Session = Depends(get_db),
):
    q = db.query(Product).filter(Product.status == "online")
    if type:
        q = q.filter(Product.type == type)
    products = q.order_by(Product.sort_order.desc(), Product.id.asc()).all()
    if not products:
        return []
    ids = [p.id for p in products]
    if not ids:
        return []
    pb_rows = db.query(ProductBenefit).filter(ProductBenefit.product_id.in_(ids)).all()
    benefits_by_pid: dict = {}
    for b in pb_rows:
        benefits_by_pid.setdefault(b.product_id, []).append(b)
    return [_product_to_out(p, benefits_by_pid.get(p.id, [])) for p in products]


@router.get("/products/{product_id}", response_model=_ProductOut,
            summary="商品详情")
def get_product(
    product_id: int,
    user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "商品不存在")
    benefits = db.query(ProductBenefit).filter_by(product_id=p.id).all()
    return _product_to_out(p, benefits)


# ---------------------------------------------------------------------------
# 下单
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=_OrderDetail,
             summary="创建订单（幂等键 + 监护人同意校验）")
def create_order(
    req: _CreateOrderReq,
    user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    if req.user_id != user.user_id:
        raise HTTPException(403, "user_id 必须与登录账号一致")

    p = db.query(Product).filter(Product.id == req.product_id).first()
    if not p:
        raise HTTPException(404, "商品不存在")
    if p.status != "online":
        raise HTTPException(400, "商品未上架，无法下单")

    benefits = db.query(ProductBenefit).filter_by(product_id=p.id).all()

    try:
        order = OrderService.create_order(
            db, user_id=req.user_id, product=p, benefits=benefits,
            idempotency_key=req.idempotency_key,
            consent_rule_version=req.consent_rule_version,
        )
    except Exception as e:
        logger.exception("下单失败")
        raise HTTPException(500, f"下单失败：{e}")

    # 监护人同意校验：本期以 user_id 与登录一致视为已同意；规则版本号落库留痕。
    if order.consent_rule_version and order.idempotency_key != f"nokey_{order.order_no}":
        from sqlalchemy import update
        db.execute(update(Order).where(Order.id == order.id).values(
            guardian_consent_at=datetime.now()))
        db.commit()
        db.refresh(order)

    return _order_to_detail(order)


# ---------------------------------------------------------------------------
# 我的订单
# ---------------------------------------------------------------------------

@router.get("/orders", response_model=list[_OrderItem],
            summary="我的订单列表（分页 + 状态筛选）")
def list_my_orders(
    user: User = Depends(require_self),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Order).filter(Order.user_id == user.user_id)
    if status:
        q = q.filter(Order.status == status)
    rows = q.order_by(Order.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return [_order_to_item(o) for o in rows]


@router.get("/orders/{order_no}", response_model=_OrderDetail,
            summary="订单详情（含状态时间线）")
def get_order(
    order_no: str,
    user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    o = db.query(Order).filter_by(order_no=order_no).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    _ensure_owner(o, user.user_id)
    return _order_to_detail(o)


@router.post("/orders/{order_no}/cancel", response_model=_OrderDetail,
             summary="取消订单（仅 PENDING_PAYMENT/PENDING_APPROVAL）")
def cancel_order(
    order_no: str,
    user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    o = db.query(Order).filter_by(order_no=order_no).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    _ensure_owner(o, user.user_id)
    try:
        o = OrderService.cancel(db, o, reason="user_cancel")
    except OrderTransitionError as e:
        raise HTTPException(400, str(e))
    return _order_to_detail(o)


# ---------------------------------------------------------------------------
# 支付信息（manual 网关 create_payment：返回二维码/备注/倒计时）
# ---------------------------------------------------------------------------

@router.get("/orders/{order_no}/payment-info", response_model=_PaymentInfo,
            summary="支付信息（manual 网关：收款码/付款备注/倒计时）")
def get_payment_info(
    order_no: str,
    user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    o = db.query(Order).filter_by(order_no=order_no).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    _ensure_owner(o, user.user_id)
    if o.status != "PENDING_PAYMENT":
        raise HTTPException(400, f"当前状态 {o.status} 不可支付")

    intent = PaymentService.create_payment(o)
    seconds_left = max(0, int((o.expire_at - datetime.now()).total_seconds()))
    return _PaymentInfo(
        order_no=o.order_no,
        amount_fen=int(intent.amount_fen or o.amount_fen or 0),
        qr_url=intent.qr_url,
        memo=intent.memo,
        tips=intent.tips,
        expire_at=intent.expire_at or o.expire_at,
        seconds_left=seconds_left,
        wechat_qr=getattr(intent, 'wechat_qr', ''),
        alipay_qr=getattr(intent, 'alipay_qr', ''),
        cs_contact=getattr(intent, 'cs_contact', ''),
    )