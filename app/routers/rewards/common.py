"""奖励闭环：家长兑换券 + 孩子心愿单（shared：constants / schemas / helpers）

本文件只承载跨子模块共享的定义，不含任何路由。router 定义在包 __init__.py。
"""
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.reward import WishItem

COUPON_KINDS = {"cartoon": "动画时间", "snack": "零食券", "sticker": "贴纸券",
                "toy": "玩具券", "outing": "外出券", "custom": "自定义"}

# 心愿目标数值由家长把关（确认/兑现均需家长密码），系统只限范围不强制下限
WISH_MIN_TARGET = 1


class CouponReq(BaseModel):
    user_id: str
    title: str
    kind: str = "custom"
    max_per_month: int = 2
    reason: str = ""  # 发券理由（成长奖励记录）
    required_days: int = 0  # 需全勤天数才可获得 1 张；0 = 添加即获得（即时券）
    required_within_days: int = 0  # 必须在多少天内达成 required_days 全勤；0 = 不限期


class WishReq(BaseModel):
    user_id: str
    title: str
    target: int = 10
    wish_type: str = "task_count"  # task_count / optional_streak
    daily_target: int = 3  # 每天需完成的可选任务数（仅 optional_streak）
    deadline: str = ""  # 截止日期 YYYY-MM-DD（空=不限期）


class ToggleReq(BaseModel):
    user_id: str


class RedeemReq(BaseModel):
    user_id: str
    reason: str = ""  # 兑现理由（成长奖励记录）


class ParentNoteReq(BaseModel):
    user_id: str
    note: str = ""


def _coupon_out(c):
    # 计算限期窗口剩余天数（仅当设置了 required_within_days 且 required_days>0）
    days_left = None
    cycle_deadline = None
    if (c.required_days or 0) > 0 and (c.required_within_days or 0) > 0 and c.cycle_start_date:
        from datetime import date, timedelta
        try:
            start = date.fromisoformat(str(c.cycle_start_date))
            deadline = start + timedelta(days=c.required_within_days)
            cycle_deadline = str(deadline)
            days_left = (deadline - date.today()).days
        except Exception:
            days_left = None
    return {
        "id": c.id, "title": c.title, "kind": c.kind,
        "kind_label": COUPON_KINDS.get(c.kind, "自定义"),
        "max_per_month": c.max_per_month, "used_count": c.used_count,
        "reason": c.reason or "", "status": c.status,
        "required_days": c.required_days or 0,
        "required_within_days": c.required_within_days or 0,
        "cycle_start_date": str(c.cycle_start_date) if c.cycle_start_date else "",
        "cycle_deadline": cycle_deadline or "",
        "days_left": days_left,
        "progress_days": c.progress_days or 0,
        "granted_count": c.granted_count or 0,
        "redeemed_count": c.redeemed_count or 0,
        "left": max(0, (c.granted_count or 0) - (c.redeemed_count or 0)),
    }


def _wish_out(w):
    return {
        "id": w.id, "title": w.title, "progress": w.progress, "target": w.target,
        "status": w.status, "redeem_reason": w.redeem_reason or "",
        "created_at": str(w.created_at)[:10] if w.created_at else "",
        "wish_type": getattr(w, 'wish_type', 'task_count') or 'task_count',
        "daily_target": getattr(w, 'daily_target', 0) or 0,
        "deadline": str(w.deadline)[:10] if getattr(w, 'deadline', None) else "",
    }


def _expire_wishes(db: Session, user_id: str):
    """将超过截止日期仍未完成的心愿置为 expired（幂等）"""
    from datetime import date
    today = date.today()
    expired = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status.in_(("active", "pending")),
        WishItem.deadline != None, WishItem.deadline < today,
    ).all()
    for w in expired:
        w.status = "expired"
        w.updated_at = datetime.now()
    if expired:
        db.commit()


__all__ = [
    "COUPON_KINDS",
    "WISH_MIN_TARGET",
    "CouponReq",
    "WishReq",
    "ToggleReq",
    "RedeemReq",
    "ParentNoteReq",
    "_coupon_out",
    "_wish_out",
    "_expire_wishes",
]
