"""钻石管理 API：余额查询、增减钻石（管理接口）"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import RECHARGE_WECHAT_QR, RECHARGE_ALIPAY_QR, RECHARGE_CS_CONTACT, RECHARGE_RATE
from ..services import diamond as diamond_svc
from .admin import _require_admin
from app.domains.identity.routers.auth import require_self

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diamond", tags=["diamond"])


@router.get("/balance", summary="查询用户钻石余额", dependencies=[Depends(require_self)])
def get_balance(
    user_id: str = Query(..., description="用户名"),
    db: Session = Depends(get_db),
):
    """返回用户当前钻石余额（首次查询自动创建账户并赠送初始钻石）"""
    balance = diamond_svc.get_balance(db, user_id)
    return {"user_id": user_id, "balance": balance}


class AdjustRequest(BaseModel):
    """增减钻石请求"""
    user_id: str = Field(..., description="用户名")
    amount: float = Field(..., description="变动数量（正=增加，负=扣除）")
    reason: str = Field("admin_adjust", description="原因说明")


@router.post("/adjust", summary="增减钻石（管理接口，需管理员）", dependencies=[Depends(_require_admin)])
def adjust_diamonds(req: AdjustRequest, db: Session = Depends(get_db)):
    """管理员增减用户钻石。amount 为正时增加，为负时扣除。"""
    if req.amount == 0:
        raise HTTPException(400, "变动数量不能为 0")
    # 校验用户存在
    from ..models.user import User
    if not db.query(User).filter(User.user_id == req.user_id).first():
        raise HTTPException(404, f"用户 {req.user_id} 不存在")
    if req.amount > 0:
        new_balance = diamond_svc.grant(db, req.user_id, req.amount, reason=req.reason)
    else:
        # 扣除
        balance = diamond_svc.get_balance(db, req.user_id)
        if balance < abs(req.amount):
            raise HTTPException(400, f"余额不足（当前 {balance}，需扣除 {abs(req.amount)}）")
        ok = diamond_svc.deduct(db, req.user_id, abs(req.amount), reason=req.reason)
        if not ok:
            raise HTTPException(400, "扣除失败")
        new_balance = diamond_svc.get_balance(db, req.user_id)
    return {"user_id": req.user_id, "amount": req.amount, "balance": new_balance}


class GrantAllRequest(BaseModel):
    """全员赠送请求"""
    amount: float = Field(1000000.0, description="赠送数量")


@router.post("/grant-all", summary="为所有用户赠送钻石（首次初始化，需管理员）", dependencies=[Depends(_require_admin)])
def grant_all(req: GrantAllRequest, db: Session = Depends(get_db)):
    """为所有尚未创建钻石账户的用户赠送指定数量钻石"""
    count = diamond_svc.grant_all_existing(db, req.amount)
    return {"granted_count": count, "amount_per_user": req.amount}


@router.get("/ledger", summary="查询钻石收支明细", dependencies=[Depends(require_self)])
def get_ledger(
    user_id: str = Query(..., description="用户名"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """返回用户最近的钻石收支记录"""
    from ..models.diamond import DiamondLedger
    records = (
        db.query(DiamondLedger)
        .filter(DiamondLedger.user_id == user_id)
        .order_by(DiamondLedger.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "amount": r.amount,
            "balance_after": r.balance_after,
            "reason": r.reason,
            "created_at": str(r.created_at) if r.created_at else "",
        }
        for r in records
    ]


@router.get("/recharge/config", summary="钻石充值配置（收款二维码 / 客服 / 汇率）")
def recharge_config():
    """返回手动充值所需的前端配置（无需登录）。

    内容：微信收款二维码、支付宝收款二维码、客服微信（仅文字 ID，便于用户手动添加）、汇率（1 元 = rate 钻石）。
    注意：刻意不返回客服「加好友二维码」(cs_wx_qr)，避免在公开接口泄露个人微信二维码；
          支付收款码（微信/支付宝）与汇率保持公开，供用户扫码付款。
    充值流程：用户扫码付款 → 在转账留言/备注填写自己的账号 → 客服核对后通过管理接口手动发放钻石。
    """
    return {
        "wechat_qr": RECHARGE_WECHAT_QR,
        "alipay_qr": RECHARGE_ALIPAY_QR,
        "cs_contact": RECHARGE_CS_CONTACT,
        "rate": RECHARGE_RATE,
    }
