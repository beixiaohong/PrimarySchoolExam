"""钻石管理 API：余额查询、增减钻石（管理接口）"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import diamond as diamond_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diamond", tags=["diamond"])


@router.get("/balance", summary="查询用户钻石余额")
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


@router.post("/adjust", summary="增减钻石（管理接口）")
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


@router.post("/grant-all", summary="为所有用户赠送钻石（首次初始化）")
def grant_all(req: GrantAllRequest, db: Session = Depends(get_db)):
    """为所有尚未创建钻石账户的用户赠送指定数量钻石"""
    count = diamond_svc.grant_all_existing(db, req.amount)
    return {"granted_count": count, "amount_per_user": req.amount}


@router.get("/ledger", summary="查询钻石收支明细")
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
