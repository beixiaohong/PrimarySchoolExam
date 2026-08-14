"""奖励闭环：兑换券管理（孩子总览 / 家长面板 / 增删改核销）"""
from datetime import datetime

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.parent_guard import ensure_parent_pwd
from app.models.reward import RewardCoupon, WishItem

from . import router
from .common import (
    COUPON_KINDS,
    CouponReq,
    ToggleReq,
    _coupon_out,
    _expire_wishes,
)


@router.get("/overview", summary="孩子侧奖励总览：可用券 + 进行中心愿 + 本周兑现数")
def rewards_overview(user_id: str, db: Session = Depends(get_db)):
    """孩子侧奖励总览：可用兑换券 + 当前进行中心愿 + 近 7 天兑现数。

    参数（Query）：user_id。
    返回：{coupons[可用券], wish(进行中或 null), redeemed_7d}。
    副作用：只读（会顺带将过期心愿标为 expired，幂等）。无需家长密码。
    """
    _expire_wishes(db, user_id)
    coupons = db.query(RewardCoupon).filter(
        RewardCoupon.user_id == user_id, RewardCoupon.status == "active",
    ).order_by(RewardCoupon.id.asc()).all()
    wish = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status.in_(("pending", "active", "pending_redeem")),
    ).order_by(WishItem.id.desc()).first()
    # 本周兑现数
    from datetime import timedelta, date
    week_ago = datetime.combine(date.today() - timedelta(days=7), datetime.min.time())
    redeemed = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status == "redeemed",
        WishItem.updated_at >= week_ago,
    ).count()
    return {
        "coupons": [_coupon_out(c) for c in coupons],
        "wish": _wish_out(wish) if wish else None,
        "redeemed_7d": redeemed,
    }


@router.get("/parent-panel", summary="家长侧管理面板：全部兑换券 + 全部待处理心愿")
def parent_panel(user_id: str, db: Session = Depends(get_db)):
    """家长侧管理面板：全部兑换券 + 全部未完结心愿（待确认/进行中/待兑现）。

    参数（Query）：user_id。
    返回：{coupons[全部券], wishes[未完结心愿]}。
    副作用：只读（顺带过期检查，幂等）。无需家长密码。
    """
    _expire_wishes(db, user_id)
    coupons = db.query(RewardCoupon).filter(
        RewardCoupon.user_id == user_id,
    ).order_by(RewardCoupon.id.desc()).all()
    wishes = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status.in_(("pending", "active", "pending_redeem")),
    ).order_by(WishItem.id.desc()).all()
    return {
        "coupons": [_coupon_out(c) for c in coupons],
        "wishes": [_wish_out(w) for w in wishes],
    }


@router.post("/coupon", summary="家长创建兑换券（需家长密码）")
def create_coupon(req: CouponReq, request: Request, db: Session = Depends(get_db)):
    """家长创建兑换券。

    参数（Body）：user_id、title、kind（cartoon/snack/sticker/toy/outing/custom）、
                  max_per_month（默认 2）、reason、required_days（0=即时券，>0=需全勤天数）、
                  required_within_days（0=不限期；>0=必须在指定天数内达成 required_days 全勤，否则该周期进度清零重启）。
    请求头：需 X-Parent-Pwd（ensure_parent_pwd 校验，否则 403）。
    返回：券详情；title 空/类型非法返回 400。
    副作用：写 reward_coupons；max_per_month 夹到 1-12，required_days 夹到 0-30，required_within_days 夹到 0-365。
    需要家长密码。
    """
    from datetime import date
    ensure_parent_pwd(db, req.user_id, request)
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "券名不能为空")
    if req.kind not in COUPON_KINDS:
        raise HTTPException(400, f"券类型只能是 {list(COUPON_KINDS)}")
    max_n = max(1, min(12, req.max_per_month or 2))  # 每月上限夹到 1-12
    rd = max(0, min(30, req.required_days or 0))  # 所需全勤天数夹到 0-30（0=即时券）
    within = max(0, min(365, req.required_within_days or 0))  # 限期天数夹到 0-365（0=不限期）
    # 限期不能短于所需全勤天数（否则永远达不成），parent 端有提示，后端兜底夹取
    if within and within < rd:
        within = rd
    c = RewardCoupon(user_id=req.user_id, title=title[:100], kind=req.kind,
                     max_per_month=max_n, status="active",
                     reason=(req.reason or "").strip()[:200] or None,
                     required_days=rd, required_within_days=within,
                     cycle_start_date=str(date.today()) if rd > 0 else None,
                     granted_count=0 if rd > 0 else 1)
    db.add(c)
    db.commit()
    return _coupon_out(c)


@router.post("/coupon/{cid}/redeem", summary="家长核销一张兑换券（需家长密码）")
def redeem_coupon(cid: int, req: ToggleReq, request: Request, db: Session = Depends(get_db)):
    """家长核销一张兑换券（granted-redeemed 剩余>0 才能核销）。

    参数（Path）：cid 券主键。参数（Body）：user_id。
    请求头：需 X-Parent-Pwd。返回：券详情；不存在 404、已停用 400、无剩余 400。
    副作用：redeemed_count+1。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
    c = db.query(RewardCoupon).filter(RewardCoupon.id == cid,
                                      RewardCoupon.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "兑换券不存在")
    if c.status != "active":
        raise HTTPException(400, "该券已停用")
    left = (c.granted_count or 0) - (c.redeemed_count or 0)
    if left <= 0:
        raise HTTPException(400, "没有可核销的券")
    c.redeemed_count = (c.redeemed_count or 0) + 1
    db.commit()
    return _coupon_out(c)


@router.post("/coupon/{cid}/toggle", summary="家长启用/停用兑换券（需家长密码）")
def toggle_coupon(cid: int, req: ToggleReq, request: Request, db: Session = Depends(get_db)):
    """家长启用/停用兑换券（active ↔ archived 切换）。

    参数（Path）：cid。参数（Body）：user_id。请求头：需 X-Parent-Pwd。
    返回：券详情；不存在 404。
    副作用：切换 status。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
    c = db.query(RewardCoupon).filter(RewardCoupon.id == cid,
                                      RewardCoupon.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "兑换券不存在")
    c.status = "active" if c.status != "active" else "archived"
    db.commit()
    return _coupon_out(c)


@router.delete("/coupon/{cid}", summary="家长删除兑换券（需家长密码）")
def delete_coupon(cid: int, request: Request, user_id: str = Query(...), db: Session = Depends(get_db)):
    """家长删除兑换券（须先停用且无未核销券）。

    参数（Path）：cid。参数（Query）：user_id。请求头：需 X-Parent-Pwd。
    返回：{ok: True}；未停用 400、仍有剩余 400、不存在 404。
    副作用：删除券记录。需要家长密码。
    """
    ensure_parent_pwd(db, user_id, request)
    c = db.query(RewardCoupon).filter(RewardCoupon.id == cid,
                                      RewardCoupon.user_id == user_id).first()
    if not c:
        raise HTTPException(404, "兑换券不存在")
    # 检查是否可以删除：必须已停用，且没有未核销的券
    if c.status != "archived":
        raise HTTPException(400, "请先停用该券再删除")
    left = (c.granted_count or 0) - (c.redeemed_count or 0)
    if left > 0:
        raise HTTPException(400, f"还有 {left} 张未核销的券，无法删除")
    db.delete(c)
    db.commit()
    return {"ok": True}


__all__ = [
    "rewards_overview",
    "parent_panel",
    "create_coupon",
    "redeem_coupon",
    "toggle_coupon",
    "delete_coupon",
]
