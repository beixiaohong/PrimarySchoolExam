"""管理后台：用户资产流水"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.diamond import DiamondAccount, DiamondLedger
from app.models.makeup_card import MakeupCard, MakeupUsageLog
from app.models.pet import CoinLedger
from app.models.reward import RewardCoupon
from app.models.user import User

from . import router
from .common import _require_admin


# 金币：coin_ledger（余额=SUM(amount)，逐笔无余额快照，后端累计推算）
# 钻石：diamond_ledger（含 balance_after 快照）
# 补签卡：makeup_usage_log（每次使用 -1）
# 卡券：reward_coupons（无逐笔时间戳，按持有量展示 granted/redeemed）

LEDGER_KINDS = {"coin": "金币", "diamond": "钻石", "makeup": "补签卡", "coupon": "卡券"}


@router.get("/users/{user_id}/ledger",
            summary="用户资产流水（金币/钻石/补签卡/卡券）")
def user_ledger(user_id: str, kind: str = "all", page: int = 1, page_size: int = 30,
                db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """查询指定用户的资产流水（金币/钻石/补签卡/卡券），支持类型过滤与分页，并汇总当前持有量。

    参数：
        user_id：目标用户 id。
        kind：资产类型（coin/diamond/makeup/coupon 或 all）。
        page / page_size：分页参数。
    业务约束：用户不存在返回 404。
    返回：{"total","page","page_size","items","balance"}；金币按逐笔累计推算余额，钻石取快照，补签卡回推余额。
    副作用：只读。
    """
    uid = user_id.strip()
    if not db.query(User).filter(User.user_id == uid).first():
        raise HTTPException(404, "用户不存在")
    want = lambda k: kind in ("all", k)
    rows = []

    if want("coin"):
        running = 0
        for r in db.query(CoinLedger).filter(CoinLedger.user_id == uid).order_by(
                CoinLedger.created_at, CoinLedger.id).all():
            running += r.amount
            rows.append({"time": r.created_at, "kind": "coin", "kind_name": "金币",
                         "amount": r.amount, "balance_after": running, "reason": r.reason,
                         "ref_id": 0})
    if want("diamond"):
        for r in db.query(DiamondLedger).filter(DiamondLedger.user_id == uid).order_by(
                DiamondLedger.created_at, DiamondLedger.id).all():
            rows.append({"time": r.created_at, "kind": "diamond", "kind_name": "钻石",
                         "amount": r.amount, "balance_after": r.balance_after,
                         "reason": r.reason, "ref_id": r.ref_id})
    if want("makeup"):
        card = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
        bal = card.balance if card else 0
        usage = db.query(MakeupUsageLog).filter(MakeupUsageLog.user_id == uid).order_by(
            MakeupUsageLog.used_at).all()
        running = bal + len(usage)  # 回推每次使用前的余额
        for r in usage:
            running -= 1
            rows.append({"time": r.used_at, "kind": "makeup", "kind_name": "补签卡",
                         "amount": -1, "balance_after": running,
                         "reason": f"补签 {r.target_date}（{r.status}）", "ref_id": r.task_id or 0})
    if want("coupon"):
        for r in db.query(RewardCoupon).filter(RewardCoupon.user_id == uid).all():
            rows.append({"time": r.created_at, "kind": "coupon", "kind_name": "卡券",
                         "amount": r.granted_count,
                         "balance_after": r.granted_count - r.redeemed_count,
                         "reason": f"{r.title}（已兑换 {r.redeemed_count}/{r.granted_count}，类型 {r.kind}）",
                         "ref_id": r.id})

    rows.sort(key=lambda x: x["time"] or datetime.min, reverse=True)
    total = len(rows)
    start = max(0, (page - 1) * page_size)
    items = rows[start:start + page_size]
    for r in items:
        r["time"] = r["time"].strftime("%Y-%m-%d %H:%M") if r["time"] else ""
    # 当前持有量汇总
    coin_bal = db.query(func.sum(CoinLedger.amount)).filter(CoinLedger.user_id == uid).scalar() or 0
    dia_acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == uid).first()
    dia_bal = dia_acc.balance if dia_acc else 0.0
    mk = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
    mk_bal = mk.balance if mk else 0
    return {"total": total, "page": page, "page_size": page_size, "items": items,
            "balance": {"coin": int(coin_bal), "diamond": round(dia_bal, 2), "makeup": mk_bal}}


__all__ = ["LEDGER_KINDS", "user_ledger"]
