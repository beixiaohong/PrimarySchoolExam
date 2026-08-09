"""奖励闭环：家长兑换券 + 孩子心愿单

表（005 迁移已建）：
- reward_coupons：家长创建的兑换券（kind: cartoon/snack/sticker/toy/outing/custom）
- wish_items：孩子心愿单。状态机：
    pending（孩子创建，待家长确认）→ active（确认后进行中）
    → progress 达 target 自动 pending_redeem（待兑现）→ redeemed（家长确认兑现，周报数据源）
  任意非 redeemed 状态可 archive 移除。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()

COUPON_KINDS = {"cartoon": "动画时间", "snack": "零食券", "sticker": "贴纸券",
                "toy": "玩具券", "outing": "外出券", "custom": "自定义"}


class CouponReq(BaseModel):
    user_id: str
    title: str
    kind: str = "custom"
    max_per_month: int = 2
    reason: str = ""  # 发券理由（成长奖励记录）
    required_days: int = 0  # 需全勤天数才可获得 1 张；0 = 添加即获得（即时券）


class WishReq(BaseModel):
    user_id: str
    title: str
    target: int = 10
    wish_type: str = "task_count"  # task_count / optional_streak
    daily_target: int = 3  # 每天需完成的可选任务数（仅 optional_streak）


class ToggleReq(BaseModel):
    user_id: str


class RedeemReq(BaseModel):
    user_id: str
    reason: str = ""  # 兑现理由（成长奖励记录）


class ParentNoteReq(BaseModel):
    user_id: str
    note: str = ""


def _coupon_out(c):
    return {
        "id": c.id, "title": c.title, "kind": c.kind,
        "kind_label": COUPON_KINDS.get(c.kind, "自定义"),
        "max_per_month": c.max_per_month, "used_count": c.used_count,
        "reason": c.reason or "", "status": c.status,
        "required_days": c.required_days or 0,
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
    }


# ═══════════════════ 兑换券 ═══════════════════

@router.get("/overview", summary="孩子侧奖励总览：可用券 + 进行中心愿 + 本周兑现数")
def rewards_overview(user_id: str, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon, WishItem
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
    from ..models.reward import RewardCoupon, WishItem
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


@router.post("/coupon", summary="家长创建兑换券")
def create_coupon(req: CouponReq, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "券名不能为空")
    if req.kind not in COUPON_KINDS:
        raise HTTPException(400, f"券类型只能是 {list(COUPON_KINDS)}")
    max_n = max(1, min(12, req.max_per_month or 2))
    rd = max(0, min(30, req.required_days or 0))
    c = RewardCoupon(user_id=req.user_id, title=title[:100], kind=req.kind,
                     max_per_month=max_n, status="active",
                     reason=(req.reason or "").strip()[:200] or None,
                     required_days=rd,
                     granted_count=0 if rd > 0 else 1)
    db.add(c)
    db.commit()
    return _coupon_out(c)


@router.post("/coupon/{cid}/redeem", summary="家长核销一张兑换券")
def redeem_coupon(cid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon
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


@router.post("/coupon/{cid}/toggle", summary="家长启用/停用兑换券")
def toggle_coupon(cid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon
    c = db.query(RewardCoupon).filter(RewardCoupon.id == cid,
                                      RewardCoupon.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "兑换券不存在")
    c.status = "active" if c.status != "active" else "archived"
    db.commit()
    return _coupon_out(c)


@router.delete("/coupon/{cid}", summary="家长删除兑换券")
def delete_coupon(cid: int, user_id: str = Query(...), db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon
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


# ═══════════════════ 心愿单 ═══════════════════

@router.post("/wish", summary="孩子创建心愿（待家长确认；同时仅 1 个进行中）")
def create_wish(req: WishReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "心愿不能为空")
    active = db.query(WishItem).filter(
        WishItem.user_id == req.user_id,
        WishItem.status.in_(("active", "pending", "pending_redeem")),
    ).first()
    if active:
        raise HTTPException(400, "已有进行中的心愿，完成或移除后才能换新的")
    target = max(1, min(100, req.target or 10))
    wish_type = req.wish_type if req.wish_type in ("task_count", "optional_streak") else "task_count"
    daily_target = max(1, min(10, req.daily_target or 3))
    w = WishItem(user_id=req.user_id, title=title[:100], target=target,
                 progress=0, status="pending",
                 wish_type=wish_type, daily_target=daily_target)
    db.add(w)
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/confirm", summary="家长确认心愿开始进行")
def confirm_wish(wid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status != "pending":
        raise HTTPException(400, "只有待确认的心愿可以开始")
    w.status = "active"
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/redeem", summary="家长确认兑现心愿")
def redeem_wish(wid: int, req: RedeemReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status != "pending_redeem":
        raise HTTPException(400, "心愿还没完成，先完成再兑现哦")
    w.status = "redeemed"
    w.redeem_reason = (req.reason or "").strip()[:200] or None
    w.updated_at = datetime.now()
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/archive", summary="移除心愿（已兑现的记录保留）")
def archive_wish(wid: int, req: ToggleReq, db: Session = Depends(get_db)):
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status == "redeemed":
        raise HTTPException(400, "已兑现的心愿是荣誉记录，不能移除")
    w.status = "archived"
    db.commit()
    return _wish_out(w)


def inc_active_wish_progress(db: Session, user_id: str, n: int = 1):
    """每日任务完成时调用：进行中心愿 progress +n，达标自动转待兑现。
    对于 optional_streak 类型，由 check_wish_optional_streak 处理。
    """
    from ..models.reward import WishItem
    w = db.query(WishItem).filter(
        WishItem.user_id == user_id, WishItem.status == "active",
    ).order_by(WishItem.id.desc()).first()
    if not w:
        return None
    # optional_streak 类型由专门的函数处理
    if getattr(w, 'wish_type', 'task_count') == 'optional_streak':
        return check_wish_optional_streak(db, user_id)
    w.progress = (w.progress or 0) + n
    if w.progress >= w.target:
        w.progress = w.target
        w.status = "pending_redeem"
    w.updated_at = datetime.now()
    db.commit()
    return _wish_out(w)


def check_wish_optional_streak(db: Session, user_id: str):
    """检查今天可选任务完成情况，更新 optional_streak 类型许愿进度"""
    from datetime import date, timedelta
    from ..models.reward import WishItem
    from ..models.daily_task import DailyTask
    today = date.today()

    w = db.query(WishItem).filter(
        WishItem.user_id == user_id, WishItem.status == "active",
        WishItem.wish_type == 'optional_streak',
    ).order_by(WishItem.id.desc()).first()
    if not w:
        return None

    daily_m = getattr(w, 'daily_target', 0) or 3  # 每天需完成的可选任务数
    last_date = getattr(w, 'last_progress_date', None)

    # 今天是否已处理过
    if last_date == today:
        return _wish_out(w)

    # 统计今天可选任务完成数
    optional_done = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today,
        DailyTask.task_type == "optional", DailyTask.status == "done",
    ).count()

    if optional_done >= daily_m:
        # 达标：连续天数 +1
        if last_date and (today - last_date).days == 1:
            w.progress = (w.progress or 0) + 1
        elif last_date and (today - last_date).days > 1:
            # 中断了，从头开始
            w.progress = 1
        else:
            w.progress = 1
        w.last_progress_date = today
    else:
        # 未达标：如果昨天也没达标，中断连续
        if last_date and (today - last_date).days > 1:
            w.progress = 0

    if w.progress >= w.target:
        w.progress = w.target
        w.status = "pending_redeem"
    w.updated_at = datetime.now()
    db.commit()
    return _wish_out(w)


def sync_coupon_progress(db: Session, user_id: str):
    """每日任务刷新时调用：今天强制任务全勤 → 每张需天数的券当日累计 1 天。
    
    规则：
    - 达到 required_days 自动获得 1 张（进度清零，可继续累计下一张）
    - 中断超过 3 天未全勤 → 进度清零
    - 每 7 天最多允许 1 天缺卡，超出则进度从头统计
    """
    from datetime import date, timedelta
    from ..models.daily_task import DailyTask
    from ..models.reward import RewardCoupon
    from ..models.makeup_card import MakeupUsageLog
    today = date.today()
    today_str = str(today)

    # 检查今天强制任务是否全勤
    mandatory_rows = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today,
        DailyTask.task_type == "mandatory",
    ).all()
    if len(mandatory_rows) < 3 or not all(r.status == "done" for r in mandatory_rows):
        return  # 今天尚未全勤，不累计

    # 检查最近 7 天的缺卡情况
    miss_count = 0
    active_days = 0  # 有任务记录的天数
    for i in range(7):
        d = today - timedelta(days=i)
        if i == 0:
            continue  # 今天已确认全勤
        # 检查该天是否全勤（强制任务全 done）
        day_rows = db.query(DailyTask).filter(
            DailyTask.user_id == user_id, DailyTask.task_date == d,
            DailyTask.task_type == "mandatory",
        ).all()
        if not day_rows:
            continue  # 该天无任务记录（用户未使用系统），不算缺卡
        active_days += 1
        day_full = len(day_rows) >= 3 and all(r.status == "done" for r in day_rows)
        if not day_full:
            # 检查是否用了补签卡
            makeup = db.query(MakeupUsageLog).filter(
                MakeupUsageLog.user_id == user_id, MakeupUsageLog.target_date == d
            ).count()
            if not makeup:
                miss_count += 1

    changed = False
    for c in db.query(RewardCoupon).filter(
            RewardCoupon.user_id == user_id, RewardCoupon.status == "active",
            RewardCoupon.required_days > 0).all():
        if c.progress_date == today_str:
            continue  # 今天已累计过
        # 中断超过 3 天 → 进度清零
        if c.progress_date and (c.progress_days or 0) > 0:
            try:
                from datetime import datetime as _dt
                last = _dt.strptime(c.progress_date, "%Y-%m-%d").date()
                if (today - last).days > 3:
                    c.progress_days = 0
            except Exception:
                pass
        # 7 天内缺卡超过 1 天 → 进度清零
        if miss_count > 1:
            c.progress_days = 0
        c.progress_days = (c.progress_days or 0) + 1
        c.progress_date = today_str
        if c.progress_days >= c.required_days:
            c.granted_count = (c.granted_count or 0) + 1
            c.progress_days = 0
        changed = True
    if changed:
        db.commit()


# ═══════════════════ 成长奖励记录 ═══════════════════

@router.get("/timeline", summary="成长奖励记录：已兑现心愿 + 已发兑换券（带理由）")
def reward_timeline(user_id: str, db: Session = Depends(get_db)):
    from ..models.reward import RewardCoupon, WishItem
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
    ).order_by(RewardCoupon.created_at.desc()).all()
    for c in coupons:
        items.append({
            "kind": "coupon", "title": f"{COUPON_KINDS.get(c.kind, '自定义')}·{c.title}",
            "reason": c.reason or "家长奖励",
            "at": str(c.created_at)[:16] if c.created_at else "",
        })
    items.sort(key=lambda x: x["at"], reverse=True)
    return {"items": items[:20]}


# ═══════════════════ 家长寄语 ═══════════════════

@router.get("/parent-note", summary="获取最近一周周报的家长寄语")
def get_parent_note(user_id: str, db: Session = Depends(get_db)):
    from ..models.ai_usage import WeeklyReport
    r = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    return {"note": getattr(r, "parent_note", "") if r else ""}


@router.post("/parent-note", summary="家长写入寄语（保存到最近周报）")
def save_parent_note(req: ParentNoteReq, db: Session = Depends(get_db)):
    from ..models.ai_usage import WeeklyReport
    note = (req.note or "").strip()[:200]
    r = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == req.user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    if not r:
        # 没有周报时先建一条占位（本周）
        from datetime import date, timedelta
        monday = date.today() - timedelta(days=date.today().weekday())
        r = WeeklyReport(user_id=req.user_id, week_start=monday, content_json="{}",
                         status="pending")
        db.add(r)
        db.flush()
    r.parent_note = note
    db.commit()
    return {"note": note}
