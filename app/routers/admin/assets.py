"""管理后台：资产调整（钻石 / 金币 / 补签卡）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.diamond import DiamondAccount
from app.models.makeup_card import MakeupCard
from app.models.pet import CoinLedger
from app.models.user import User
from app.services.diamond import grant as grant_diamond

from . import router
from .common import _audit, _require_admin


class AssetAdjustReq(BaseModel):
    user_id: str
    asset: str  # diamond / coin / makeup
    amount: float
    reason: str


@router.post("/assets/adjust", summary="资产调整（钻石/金币/补签卡，必填理由）")
def adjust_assets(req: AssetAdjustReq, db: Session = Depends(get_db),
                  admin: Admin = Depends(_require_admin)):
    reason = req.reason.strip()
    if not reason:
        raise HTTPException(400, "调整理由必填")
    user = db.query(User).filter(User.user_id == req.user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    uid = user.user_id

    if req.asset == "diamond":
        acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == uid).first()
        if req.amount < 0 and (not acc or acc.balance + req.amount < 0):
            raise HTTPException(400, "扣减后余额不能为负")
        balance = grant_diamond(db, uid, req.amount, reason="admin_adjust")
        detail = f"钻石 {req.amount:+g} → 余额 {balance}"
    elif req.asset == "coin":
        amount = int(req.amount)
        if not amount:
            raise HTTPException(400, "金币数量不能为 0")
        cur = db.query(func.sum(CoinLedger.amount)).filter(
            CoinLedger.user_id == uid).scalar() or 0
        if cur + amount < 0:
            raise HTTPException(400, "扣减后余额不能为负")
        db.add(CoinLedger(user_id=uid, amount=amount, reason=f"管理员调整：{reason}"))
        db.commit()
        detail = f"金币 {amount:+d} → 余额 {cur + amount}"
    elif req.asset == "makeup":
        amount = int(req.amount)
        if not amount:
            raise HTTPException(400, "补签卡数量不能为 0")
        card = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
        if not card:
            card = MakeupCard(user_id=uid, balance=0, total_earned=0, total_used=0)
            db.add(card)
            db.flush()
        if card.balance + amount < 0:
            raise HTTPException(400, "扣减后余额不能为负")
        card.balance += amount
        if amount > 0:
            card.total_earned += amount
        db.commit()
        detail = f"补签卡 {amount:+d} → 余额 {card.balance}"
    else:
        raise HTTPException(400, "资产类型无效（diamond/coin/makeup）")

    _audit(db, admin, "assets:" + req.asset, uid, f"{detail}；理由：{reason}")
    return {"ok": True, "detail": detail}


__all__ = ["AssetAdjustReq", "adjust_assets"]
