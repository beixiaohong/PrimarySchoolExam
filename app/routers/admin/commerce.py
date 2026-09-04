"""管理后台：交易域（商品 / 订单 / 核销 / 审批）（S4-M5 / 07 §4.2）

接口（挂 /api/admin 前缀，统一 require_perm 鉴权 + _audit 落库）：

商品
- GET    /commerce/products                       商品列表（多条件筛选）        product:view
- POST   /commerce/products                       创建商品                       product:manage
- PUT    /commerce/products/{id}                  修改商品                       product:manage
- POST   /commerce/products/{id}/status           上下架（online/offline）        product:manage

订单
- GET    /commerce/orders                         订单列表（多条件筛选）         order:view_all
- GET    /commerce/orders/{id}                    订单详情（含流水 + 审计）      order:view_all
- POST   /commerce/orders/{id}/confirm-payment    核销（BR-M0-2-05）            order:confirm_payment
- POST   /commerce/orders/{id}/approve            大额审批通过                   order:confirm_payment
- POST   /commerce/orders/{id}/reject             大额审批驳回                   order:confirm_payment
- POST   /commerce/orders/{id}/refund             退款（FULFILLED→REFUNDING）    order:refund
- POST   /commerce/orders/{id}/reverse            冲正（PAID→REVERSED）         order:reverse

铁律：全部经 commerce.contracts 触达 D7 域（import-linter 合规）；全部 require_perm + _audit；
核销流程无外部阻塞（manual 网关纯校验 BR-M0-2-05）；
BR-M0-2-04 审批人 ≠ 核销人：approve 时校验最近 CONFIRM 流水的 operator_name 与当前 admin 不一致；
物理禁止：永不删除订单/流水（DB-05）。
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.commerce_order import Order
from app.models.commerce_payment import PayTransaction
from app.models.commerce_product import Product, ProductBenefit
from app.domains.commerce.contracts import (OrderService, OrderTransitionError,
                                              ConfirmPayload)

from . import router
from .common import _audit
from app.core.permissions import require_perm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 请求/响应模型（必须在路由装饰器前定义）
# ---------------------------------------------------------------------------

class _ProductUpsertReq(BaseModel):
    sku: str
    name: str
    type: str
    subtitle: str = ""
    description: Optional[str] = None
    price_fen: int
    original_fen: int
    duration_days: int = 0
    grade_scope: str = ""
    sort_order: int = 0


class _StatusReq(BaseModel):
    status: str


class _ConfirmReq(BaseModel):
    external_no: str
    received_fen: int
    channel: str = "manual"
    evidence_url: str = ""
    evidence_hash: str = ""
    remark: str = ""


class _RefundReq(BaseModel):
    reason: str = ""
    amount_fen: Optional[int] = None


class _ReverseReq(BaseModel):
    reason: str = ""


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------

def _product_to_dict(p: Product, benefits: list) -> dict:
    return {
        "id": p.id, "sku": p.sku, "name": p.name, "type": p.type,
        "subtitle": p.subtitle, "description": p.description,
        "price_fen": int(p.price_fen or 0), "original_fen": int(p.original_fen or 0),
        "duration_days": int(p.duration_days or 0), "grade_scope": p.grade_scope,
        "sort_order": int(p.sort_order or 0), "status": p.status,
        "online_at": p.online_at.isoformat() if p.online_at else None,
        "offline_at": p.offline_at.isoformat() if p.offline_at else None,
        "benefits": [{"id": b.id, "benefit_type": b.benefit_type,
                      "benefit_key": b.benefit_key, "amount": int(b.amount),
                      "sort_order": int(b.sort_order or 0)} for b in benefits],
    }


def _order_to_dict(o: Order) -> dict:
    return {
        "id": o.id, "order_no": o.order_no, "user_id": o.user_id,
        "product_id": o.product_id, "product_sku": o.product_sku,
        "product_name": o.product_name, "amount_fen": int(o.amount_fen or 0),
        "status": o.status, "expire_at": o.expire_at.isoformat() if o.expire_at else None,
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "fulfilled_at": o.fulfilled_at.isoformat() if o.fulfilled_at else None,
        "closed_at": o.closed_at.isoformat() if o.closed_at else None,
        "close_reason": o.close_reason,
        "remark": o.remark, "created_at": o.created_at.isoformat() if o.created_at else None,
    }


# ---------------------------------------------------------------------------
# 商品接口
# ---------------------------------------------------------------------------

@router.get("/commerce/products", summary="商品列表")
def admin_list_products(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("product:view")),
):
    q = db.query(Product)
    if status:
        q = q.filter(Product.status == status)
    if type:
        q = q.filter(Product.type == type)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter((Product.name.like(kw)) | (Product.sku.like(kw)))
    total = q.count()
    rows = q.order_by(Product.sort_order.desc(), Product.id.desc()).offset((page-1)*size).limit(size).all()
    if not rows:
        return {"items": [], "total": total, "page": page, "size": size}
    ids = [p.id for p in rows]
    pb_rows = db.query(ProductBenefit).filter(ProductBenefit.product_id.in_(ids)).all()
    pb_by_pid: dict = {}
    for b in pb_rows:
        pb_by_pid.setdefault(b.product_id, []).append(b)
    items = [_product_to_dict(p, pb_by_pid.get(p.id, [])) for p in rows]
    _audit(db, admin, "product_list", "products",
           f"列表 status={status} type={type} 共 {len(items)} 条")
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/commerce/products", summary="创建商品")
def admin_create_product(
    req: _ProductUpsertReq,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("product:manage")),
):
    if db.query(Product).filter_by(sku=req.sku).first():
        raise HTTPException(400, f"sku={req.sku} 已存在")
    p = Product(
        sku=req.sku, name=req.name, type=req.type, subtitle=req.subtitle,
        description=req.description, price_fen=req.price_fen,
        original_fen=req.original_fen, duration_days=req.duration_days,
        grade_scope=req.grade_scope, sort_order=req.sort_order,
        status="offline", created_by=admin.username,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    _audit(db, admin, "product_create", f"product:{p.id}",
           f"创建商品 sku={p.sku} name={p.name} price={req.price_fen}分",
           amount_fen=req.price_fen)
    return _product_to_dict(p, [])


@router.put("/commerce/products/{product_id}", summary="修改商品")
def admin_update_product(
    product_id: int,
    req: _ProductUpsertReq,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("product:manage")),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "商品不存在")
    dup = db.query(Product).filter(Product.sku == req.sku, Product.id != p.id).first()
    if dup:
        raise HTTPException(400, f"sku={req.sku} 已被其他商品占用")
    p.name = req.name
    p.type = req.type
    p.subtitle = req.subtitle
    p.description = req.description
    p.price_fen = req.price_fen
    p.original_fen = req.original_fen
    p.duration_days = req.duration_days
    p.grade_scope = req.grade_scope
    p.sort_order = req.sort_order
    p.updated_by = admin.username
    db.commit()
    db.refresh(p)
    benefits = db.query(ProductBenefit).filter_by(product_id=p.id).all()
    _audit(db, admin, "product_update", f"product:{p.id}",
           f"更新商品 sku={p.sku} price={req.price_fen}分",
           amount_fen=req.price_fen)
    return _product_to_dict(p, benefits)


@router.post("/commerce/products/{product_id}/status", summary="上下架")
def admin_set_product_status(
    product_id: int,
    req: _StatusReq,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("product:manage")),
):
    if req.status not in ("online", "offline"):
        raise HTTPException(400, "status 必须是 online/offline")
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, "商品不存在")
    p.status = req.status
    now = datetime.now()
    if req.status == "online":
        p.online_at = now
    else:
        p.offline_at = now
    p.updated_by = admin.username
    db.commit()
    _audit(db, admin, f"product_{req.status}", f"product:{p.id}",
           f"{req.status} sku={p.sku}")
    return {"id": p.id, "status": p.status,
            "online_at": p.online_at, "offline_at": p.offline_at}


# ---------------------------------------------------------------------------
# 订单接口
# ---------------------------------------------------------------------------

@router.get("/commerce/orders", summary="订单列表（多条件筛选）")
def admin_list_orders(
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    order_no: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:view_all")),
):
    q = db.query(Order)
    if status:
        q = q.filter(Order.status == status)
    if user_id:
        q = q.filter(Order.user_id == user_id)
    if product_id:
        q = q.filter(Order.product_id == product_id)
    if order_no:
        q = q.filter(Order.order_no == order_no)
    total = q.count()
    rows = q.order_by(Order.created_at.desc()).offset((page-1)*size).limit(size).all()
    _audit(db, admin, "order_list", "orders",
           f"列表 status={status} user={user_id} product={product_id} 共 {len(rows)} 条")
    return {"items": [_order_to_dict(o) for o in rows], "total": total,
            "page": page, "size": size}


@router.get("/commerce/orders/{order_id}", summary="订单详情（含流水与审计）")
def admin_order_detail(
    order_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:view_all")),
):
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    tx = db.query(PayTransaction).filter_by(order_id=o.id).order_by(
        PayTransaction.id.asc()).all()
    from app.models.admin import AdminOperationLog
    audits = db.query(AdminOperationLog).filter(
        AdminOperationLog.target == o.order_no,
        AdminOperationLog.target_type == "order",
    ).order_by(AdminOperationLog.id.asc()).all()
    _audit(db, admin, "order_detail", f"order:{o.order_no}",
           f"查看订单详情 含 {len(tx)} 条流水 {len(audits)} 条审计")
    data = _order_to_dict(o)
    data["transactions"] = [{
        "id": t.id, "action": t.action, "gateway": t.gateway,
        "amount_fen": int(t.amount_fen or 0), "received_fen": int(t.received_fen or 0),
        "external_no": t.external_no, "channel": t.channel,
        "evidence_url": t.evidence_url, "operator_name": t.operator_name,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "reason": t.reason,
    } for t in tx]
    data["audit_logs"] = [{
        "id": a.id, "admin": a.admin, "action": a.action,
        "detail": a.detail, "ip": a.ip,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in audits]
    return data


# ---------------------------------------------------------------------------
# 核销 / 审批 / 退款 / 冲正
# ---------------------------------------------------------------------------

@router.post("/commerce/orders/{order_id}/confirm-payment",
             summary="核销（BR-M0-2-05 网关层校验 + 写流水/审计）")
def admin_confirm_payment(
    order_id: int,
    req: _ConfirmReq,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:confirm_payment")),
):
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status not in ("PENDING_PAYMENT", "PENDING_APPROVAL"):
        raise HTTPException(400, f"当前状态 {o.status} 不可核销")
    payload = ConfirmPayload(
        external_no=req.external_no, received_fen=req.received_fen,
        channel=req.channel, evidence_url=req.evidence_url,
        evidence_hash=req.evidence_hash, remark=req.remark,
    )
    try:
        o = OrderService.confirm_payment(
            db, o, payload,
            operator_id=admin.id, operator_name=admin.username,
        )
    except OrderTransitionError as e:
        raise HTTPException(400, str(e))
    _audit(db, admin, "order_confirm_payment", f"order:{o.order_no}",
           f"核销实收={req.received_fen}分 流水={req.external_no}",
           amount_fen=req.received_fen)
    return _order_to_dict(o)


@router.post("/commerce/orders/{order_id}/approve",
             summary="大额审批通过（PENDING_APPROVAL → PAID，BR-M0-2-04 审批人≠核销人）")
def admin_approve_order(
    order_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:confirm_payment")),
):
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status != "PENDING_APPROVAL":
        raise HTTPException(400, f"当前状态 {o.status} 不可审批")
    last_confirm = db.query(PayTransaction).filter(
        PayTransaction.order_id == o.id, PayTransaction.action == "CONFIRM"
    ).order_by(PayTransaction.id.desc()).first()
    if last_confirm and last_confirm.operator_name == admin.username:
        raise HTTPException(403, "BR-M0-2-04：审批人不能与核销人相同")
    try:
        o = OrderService.approve(
            db, o, approver_id=admin.id, approver_name=admin.username,
        )
    except OrderTransitionError as e:
        raise HTTPException(400, str(e))
    _audit(db, admin, "order_approve", f"order:{o.order_no}",
           "大额审批通过", amount_fen=int(o.amount_fen or 0))
    return _order_to_dict(o)


@router.post("/commerce/orders/{order_id}/reject",
             summary="大额审批驳回（PENDING_APPROVAL → PENDING_PAYMENT）")
def admin_reject_order(
    order_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:confirm_payment")),
):
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status != "PENDING_APPROVAL":
        raise HTTPException(400, f"当前状态 {o.status} 不可驳回")
    try:
        o = OrderService.transition(
            db, o, "PENDING_PAYMENT", operator_id=admin.id,
            operator_name=admin.username, reason="approver_reject")
    except OrderTransitionError as e:
        raise HTTPException(400, str(e))
    _audit(db, admin, "order_reject", f"order:{o.order_no}",
           "大额审批驳回")
    return _order_to_dict(o)


@router.post("/commerce/orders/{order_id}/refund",
             summary="退款（FULFILLED → REFUNDING）")
def admin_refund_order(
    order_id: int,
    req: _RefundReq,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:refund")),
):
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status != "FULFILLED":
        raise HTTPException(400, f"当前状态 {o.status} 不可发起退款（须 FULFILLED）")
    try:
        o = OrderService.refund(
            db, o, amount_fen=req.amount_fen or int(o.amount_fen or 0),
            operator_id=admin.id, operator_name=admin.username,
            reason=req.reason,
        )
    except OrderTransitionError as e:
        raise HTTPException(400, str(e))
    _audit(db, admin, "order_refund", f"order:{o.order_no}",
           f"发起退款 {req.amount_fen or o.amount_fen}分 原因={req.reason}",
           amount_fen=req.amount_fen or int(o.amount_fen or 0))
    return _order_to_dict(o)


@router.post("/commerce/orders/{order_id}/reverse",
             summary="冲正（PAID → REVERSED）")
def admin_reverse_order(
    order_id: int,
    req: _ReverseReq,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("order:reverse")),
):
    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status != "PAID":
        raise HTTPException(400, f"当前状态 {o.status} 不可冲正（须 PAID）")
    p = ConfirmPayload(external_no="")
    p.external_no = f"reverse_{o.id}_{int(datetime.now().timestamp())}"
    p.received_fen = int(o.amount_fen or 0)
    p.remark = req.reason
    try:
        o = OrderService.transition(
            db, o, "REVERSED", operator_id=admin.id, operator_name=admin.username,
            action="REVERSE", payload=p, reason=req.reason)
    except OrderTransitionError as e:
        raise HTTPException(400, str(e))
    _audit(db, admin, "order_reverse", f"order:{o.order_no}",
           f"冲正 原因={req.reason}", amount_fen=int(o.amount_fen or 0))
    return _order_to_dict(o)