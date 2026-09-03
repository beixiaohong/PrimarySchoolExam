"""奖励闭环：孩子心愿单 + 进度推进"""
from datetime import date, datetime, timedelta

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.services.parent_guard import ensure_parent_pwd
from app.models.reward import WishItem
from app.models.daily_task import DailyTask

from . import router
from .common import (
    WISH_MIN_TARGET,
    WishReq,
    ToggleReq,
    RedeemReq,
    _wish_out,
    _expire_wishes,
)


@router.post("/wish", summary="孩子创建心愿（待家长确认；同时仅 1 个进行中）")
def create_wish(req: WishReq, db: Session = Depends(get_db)):
    """孩子创建心愿（进入 pending，待家长确认；同时仅允许 1 个进行中）。

    参数（Body）：user_id、title、target（默认 10）、wish_type（task_count/optional_streak）、
                  daily_target（仅 optional_streak）、deadline（YYYY-MM-DD，可空）。
    返回：心愿详情；title 空 400、已有进行中 400、deadline 非法/过早/超 1 年 400。
    副作用：写 wish_items（status=pending）。无需家长密码。
    """
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "心愿不能为空")
    active = db.query(WishItem).filter(
        WishItem.user_id == req.user_id,
        WishItem.status.in_(("active", "pending", "pending_redeem")),
    ).first()
    if active:
        raise HTTPException(400, "已有进行中的心愿，完成或移除后才能换新的")
    target = max(WISH_MIN_TARGET, min(100, req.target or 10))  # 目标值夹到 1-100
    wish_type = req.wish_type if req.wish_type in ("task_count", "optional_streak") else "task_count"
    daily_target = max(1, min(10, req.daily_target or 3))
    # 截止日期：须晚于今天，最长 365 天
    deadline_val = None
    if (req.deadline or "").strip():
        try:
            deadline_val = date.fromisoformat(req.deadline.strip())
        except ValueError:
            raise HTTPException(400, "截止日期格式应为 YYYY-MM-DD")
        if deadline_val <= date.today():
            raise HTTPException(400, "截止日期必须晚于今天")
        if deadline_val > date.today() + timedelta(days=365):
            raise HTTPException(400, "截止日期最长一年")
    w = WishItem(user_id=req.user_id, title=title[:100], target=target,
                 progress=0, status="pending",
                 wish_type=wish_type, daily_target=daily_target,
                 deadline=deadline_val,
                 validity_days=(deadline_val - date.today()).days if deadline_val else None)
    db.add(w)
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/confirm", summary="家长确认心愿开始进行（需家长密码）")
def confirm_wish(wid: int, req: ToggleReq, request: Request, db: Session = Depends(get_db)):
    """家长确认心愿开始进行（pending → active）。

    参数（Path）：wid。参数（Body）：user_id。请求头：需 X-Parent-Pwd。
    返回：心愿详情；不存在 404、非 pending 状态 400。
    副作用：status=pending→active。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
    w = db.query(WishItem).filter(WishItem.id == wid,
                                  WishItem.user_id == req.user_id).first()
    if not w:
        raise HTTPException(404, "心愿不存在")
    if w.status != "pending":
        raise HTTPException(400, "只有待确认的心愿可以开始")
    w.status = "active"
    db.commit()
    return _wish_out(w)


@router.post("/wish/{wid}/redeem", summary="家长确认兑现心愿（需家长密码）")
def redeem_wish(wid: int, req: RedeemReq, request: Request, db: Session = Depends(get_db)):
    """家长确认兑现心愿（pending_redeem → redeemed，进入成长记录/周报）。

    参数（Path）：wid。参数（Body）：user_id、reason。请求头：需 X-Parent-Pwd。
    返回：心愿详情；不存在 404、未完成(非 pending_redeem) 400。
    副作用：status=pending_redeem→redeemed，写 redeem_reason。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
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


@router.post("/wish/{wid}/archive", summary="移除心愿（需家长密码；已兑现的记录保留）")
def archive_wish(wid: int, req: ToggleReq, request: Request, db: Session = Depends(get_db)):
    """家长移除心愿（非 redeemed 状态 → archived；已兑现荣誉记录保留）。

    参数（Path）：wid。参数（Body）：user_id。请求头：需 X-Parent-Pwd。
    返回：心愿详情；不存在 404、已兑现 400。
    副作用：status→archived。需要家长密码。
    """
    ensure_parent_pwd(db, req.user_id, request)
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
    """可选任务完成时调用：进行中心愿 progress +n，达标自动转待兑现。
    仅统计可选任务（强制任务不计入心愿进度）。
    对于 optional_streak 类型，由 check_wish_optional_streak 处理。
    """
    _expire_wishes(db, user_id)
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
    today = date.today()

    _expire_wishes(db, user_id)
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


__all__ = [
    "create_wish",
    "confirm_wish",
    "redeem_wish",
    "archive_wish",
    "inc_active_wish_progress",
    "check_wish_optional_streak",
]
