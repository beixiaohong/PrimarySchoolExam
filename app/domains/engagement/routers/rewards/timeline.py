"""奖励闭环：成长奖励记录 + 家长寄语"""
from datetime import date, datetime, timedelta

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reward import RewardCoupon, WishItem
from app.models.ai_usage import WeeklyReport

from . import router
from .common import (
    COUPON_KINDS,
    ParentNoteReq,
)


@router.get("/timeline", summary="成长奖励记录：已兑现心愿 + 已发兑换券（带理由）")
def reward_timeline(user_id: str, db: Session = Depends(get_db)):
    """成长奖励记录：已兑现心愿 + 已发放兑换券（带理由），按时间倒序最多 20 条。

    参数（Query）：user_id。
    返回：{items[{kind, title, reason, at}]}。
    副作用：无（只读）。无需家长密码。
    """
    items = []
    wishes = db.query(WishItem).filter(
        WishItem.user_id == user_id, WishItem.status == "redeemed",
    ).order_by(WishItem.updated_at.desc()).all()
    for w in wishes:
        items.append({
            "kind": "wish", "title": w.title,
            "reason": w.redeem_reason or "心愿达成！",
            "at": str(w.updated_at)[:16] if w.updated_at else "",
        })
    coupons = db.query(RewardCoupon).filter(
        RewardCoupon.user_id == user_id, RewardCoupon.status == "active",
        RewardCoupon.granted_count > 0,  # 只记录已获取的券，创建未达标不进时间线
    ).order_by(RewardCoupon.created_at.desc()).all()
    for c in coupons:
        items.append({
            "kind": "coupon", "title": f"{COUPON_KINDS.get(c.kind, '自定义')}·{c.title}",
            "reason": c.reason or "家长奖励",
            "at": str(c.created_at)[:16] if c.created_at else "",
        })
    items.sort(key=lambda x: x["at"], reverse=True)
    return {"items": items[:20]}


@router.get("/parent-note", summary="获取最近一周周报的家长寄语")
def get_parent_note(user_id: str, db: Session = Depends(get_db)):
    """获取最近一周周报的家长寄语。

    参数（Query）：user_id。
    返回：{note}（无周报则为空串）。
    副作用：无（只读）。无需家长密码。
    """
    r = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    return {"note": getattr(r, "parent_note", "") if r else ""}


@router.post("/parent-note", summary="家长写入寄语（保存到最近周报）")
def save_parent_note(req: ParentNoteReq, db: Session = Depends(get_db)):
    """家长写入寄语，保存到最近一周周报（无周报则建一条本周占位）。

    参数（Body）：user_id、note（<=200 字）。
    返回：{note}。无需家长密码（仅写寄语，非敏感操作）。
    副作用：upsert WeeklyReport.parent_note。
    """
    note = (req.note or "").strip()[:200]
    r = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == req.user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    if not r:
        # 没有周报时先建一条占位（本周）
        monday = date.today() - timedelta(days=date.today().weekday())
        r = WeeklyReport(user_id=req.user_id, week_start=monday, content_json="{}",
                         status="pending")
        db.add(r)
        db.flush()
    r.parent_note = note
    db.commit()
    return {"note": note}


__all__ = [
    "reward_timeline",
    "get_parent_note",
    "save_parent_note",
]
