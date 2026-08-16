"""奖励闭环：家长兑换券 + 孩子心愿单（shared：constants / schemas / helpers）

本文件只承载跨子模块共享的定义，不含任何路由。router 定义在包 __init__.py。
"""
import math
from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask
from app.models.reward import WishItem

COUPON_KINDS = {"cartoon": "动画时间", "snack": "零食券", "sticker": "贴纸券",
                "toy": "玩具券", "outing": "外出券", "custom": "自定义"}

# 心愿目标数值由家长把关（确认/兑现均需家长密码），系统只限范围不强制下限
WISH_MIN_TARGET = 1


class CouponReq(BaseModel):
    """家长创建兑换券请求体：用户 ID、券名、类型、每月上限、理由及全勤获取条件。"""
    user_id: str
    title: str
    kind: str = "custom"
    max_per_month: int = 2
    reason: str = ""  # 发券理由（成长奖励记录）
    required_days: int = 0  # 需全勤天数才可获得 1 张；0 = 添加即获得（即时券）
    required_within_days: int = 0  # 必须在多少天内达成 required_days 全勤；0 = 不限期


class WishReq(BaseModel):
    """孩子创建心愿请求体：用户 ID、标题、目标值、类型、每日目标与截止日期。"""
    user_id: str
    title: str
    target: int = 10
    wish_type: str = "task_count"  # task_count / optional_streak
    daily_target: int = 3  # 每天需完成的可选任务数（仅 optional_streak）
    deadline: str = ""  # 截止日期 YYYY-MM-DD（空=不限期）


class ToggleReq(BaseModel):
    """通用切换/操作请求体：仅需用户 ID（确认、启用停用、移除等）。"""
    user_id: str


class RedeemReq(BaseModel):
    """家长兑现心愿请求体：用户 ID 与兑现理由（进入成长记录）。"""
    user_id: str
    reason: str = ""  # 兑现理由（成长奖励记录）


class ParentNoteReq(BaseModel):
    """家长寄语请求体：用户 ID 与寄语内容（<=200 字）。"""
    user_id: str
    note: str = ""


def _coupon_out(c):
    """将 RewardCoupon 模型序列化为前端展示字典：含类型标签、限额、进度、已发/已核销数与限期剩余天数。"""
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
    """将 WishItem 模型序列化为前端展示字典：含标题、进度、目标、状态、类型、每日目标与截止日期。"""
    return {
        "id": w.id, "title": w.title, "progress": w.progress, "target": w.target,
        "status": w.status, "redeem_reason": w.redeem_reason or "",
        "created_at": str(w.created_at)[:10] if w.created_at else "",
        "wish_type": getattr(w, 'wish_type', 'task_count') or 'task_count',
        "daily_target": getattr(w, 'daily_target', 0) or 0,
        "deadline": str(w.deadline)[:10] if getattr(w, 'deadline', None) else "",
        "validity_days": getattr(w, 'validity_days', None),
    }


def _wish_window_days(w: WishItem) -> int:
    """取心愿有效期天数：优先用存储的 validity_days，缺失时按 旧deadline-创建日 回算（至少 1 天）。"""
    vd = getattr(w, 'validity_days', None)
    if vd and vd > 0:
        return vd
    dl = getattr(w, 'deadline', None)
    ca = getattr(w, 'created_at', None)
    if dl and ca:
        span = (dl - ca.date()).days
        if span > 0:
            return span
    return 1


def _today_optional_count(db: Session, user_id: str) -> int:
    """今天可选任务条数（用于估算 task_count 心愿每天最多可推进的进度）。"""
    n = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == date.today(),
        DailyTask.task_type == "optional").count()
    return max(1, n)


def _reset_impossible_wishes(db: Session, user_id: str):
    """「有效期 + 清零重发」规则（心愿）：

    若心愿带 deadline 且当前状态为 active/pending，计算：
      days_remaining = deadline - 今天
      days_needed    = 完成还需的最少天数（按每天可达进度保守估算）
    当 days_remaining < days_needed（铁定无法在有效期内完成）→ 清零重发：
      progress=0、连续天数标记清空、deadline 顺延为 今天 + 原有效期天数（validity_days）。
    状态保持 active，不抹掉任务本身，给孩子一个干净的完整有效期。
    """
    today = date.today()
    rows = db.query(WishItem).filter(
        WishItem.user_id == user_id,
        WishItem.status.in_(("active", "pending")),
        WishItem.deadline != None, WishItem.deadline >= today,
    ).all()
    changed = False
    for w in rows:
        days_remaining = (w.deadline - today).days
        if w.wish_type == "optional_streak":
            # 连续天数：若昨天/今天还在连续中，已进度有效；否则视为断档从 0 起算
            last = getattr(w, 'last_progress_date', None)
            eff = w.progress or 0
            if last is None or (today - last).days > 1:
                eff = 0
            days_needed = max(0, (w.target or 0) - eff)
        else:  # task_count：每完成 1 个可选任务 +1，每天最多 = 当天可选任务数
            max_opt = _today_optional_count(db, user_id)
            remain = max(0, (w.target or 0) - (w.progress or 0))
            days_needed = math.ceil(remain / max_opt)
        if days_remaining < days_needed:
            w.progress = 0
            w.last_progress_date = None
            window = _wish_window_days(w)
            w.validity_days = window
            w.deadline = today + timedelta(days=window)
            w.updated_at = datetime.now()
            changed = True
    if changed:
        db.commit()


def _expire_wishes(db: Session, user_id: str):
    """将超过截止日期仍未完成的心愿置为 expired（幂等）；并顺带执行「必然完成不了→清零重发」。"""
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
    # 有效期规则：判「必然完成不了」并清零重发（幂等，仅对 active/pending 生效）
    _reset_impossible_wishes(db, user_id)


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
