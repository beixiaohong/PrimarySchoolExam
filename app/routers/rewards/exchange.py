"""奖励闭环：兑换券进度同步（每日任务刷新时调用）"""
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask
from app.models.reward import RewardCoupon
from app.models.makeup_card import MakeupUsageLog


def sync_coupon_progress(db: Session, user_id: str):
    """每日任务刷新时调用：今天强制任务全勤 → 每张需天数的券当日累计 1 天。

    规则：
    - 达到 required_days 自动获得 1 张（进度清零，可继续累计下一张）
    - 中断超过 3 天未全勤 → 进度清零
    - 每 7 天最多允许 1 天缺卡，超出则进度从头统计
    - 连续 2 天以上无任何任务记录（刻意停用系统）视为中断 → 进度清零
    """
    today = date.today()
    today_str = str(today)

    # 用户最早的任务记录日：此前的日期（未启用系统）不计缺卡/中断，避免新用户被误清零
    first_day = db.query(func.min(DailyTask.task_date)).filter(
        DailyTask.user_id == user_id).scalar()

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
    no_record_streak = 0   # 连续无记录天数（防刷：刻意停用系统规避缺卡统计）
    interrupted = False
    for i in range(1, 7):
        d = today - timedelta(days=i)
        if first_day and d < first_day:
            continue  # 用户启用系统前的日期不纳入统计
        # 检查该天是否全勤（强制任务全 done）
        day_rows = db.query(DailyTask).filter(
            DailyTask.user_id == user_id, DailyTask.task_date == d,
            DailyTask.task_type == "mandatory",
        ).all()
        if not day_rows:
            no_record_streak += 1
            if no_record_streak >= 2:
                interrupted = True  # 连续 2 天以上无记录 → 视为中断
            continue
        no_record_streak = 0
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
        # 硬性限期窗口：超过 required_within_days 仍未达成 → 进度清零并重启周期
        if (c.required_within_days or 0) > 0 and c.cycle_start_date:
            try:
                from datetime import datetime as _dt
                start = _dt.strptime(c.cycle_start_date, "%Y-%m-%d").date()
                if (today - start).days > c.required_within_days:
                    c.progress_days = 0
                    c.cycle_start_date = today_str
            except Exception:
                pass
        # 中断超过 3 天 → 进度清零
        if c.progress_date and (c.progress_days or 0) > 0:
            try:
                from datetime import datetime as _dt
                last = _dt.strptime(c.progress_date, "%Y-%m-%d").date()
                if (today - last).days > 3:
                    c.progress_days = 0
            except Exception:
                pass
        # 7 天内缺卡超过 1 天 或 连续无记录中断 → 进度清零
        if miss_count > 1 or interrupted:
            c.progress_days = 0
        c.progress_days = (c.progress_days or 0) + 1
        c.progress_date = today_str
        if c.progress_days >= c.required_days:
            c.granted_count = (c.granted_count or 0) + 1
            c.progress_days = 0
            # 达成后重启限期窗口，下一张也需在窗口内达成
            if (c.required_within_days or 0) > 0:
                c.cycle_start_date = today_str
        changed = True
    if changed:
        db.commit()


__all__ = [
    "sync_coupon_progress",
]
