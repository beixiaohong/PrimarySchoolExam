"""奖励闭环：兑换券进度同步（每日任务刷新时调用）"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask
from app.models.reward import RewardCoupon
from app.models.makeup_card import MakeupUsageLog


def sync_coupon_progress(db: Session, user_id: str):
    """每日任务刷新时调用：今天强制任务全勤 → 每张需天数的券当日累计 1 天。

    规则：
    - 达到 required_days 自动获得 1 张（进度清零，可继续累计下一张）
    - 中断超过 3 天未全勤 → 进度清零
    - 本轮（自本轮起点）内缺卡超过 1 天 或 连续无记录中断 → 进度清零重来
    - 连续 2 天以上无任何任务记录（刻意停用系统）视为中断 → 进度清零

    关键修复（2026-08-19）：缺卡清零后必须从「清零当天」重新起算本轮，
    只统计本轮起点之后的缺卡。旧实现每次全勤日都看「今天往前 7 天」的缺卡，
    一旦历史窗口里积了 2 次缺卡，之后即使天天全勤也会被反复清零，进度永远卡在 1。
    """
    today = date.today()
    today_str = str(today)

    # 检查今天强制任务是否全勤
    mandatory_rows = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today,
        DailyTask.task_type == "mandatory",
    ).all()
    if len(mandatory_rows) < 3 or not all(r.status == "done" for r in mandatory_rows):
        return  # 今天尚未全勤，不累计

    changed = False
    for c in db.query(RewardCoupon).filter(
            RewardCoupon.user_id == user_id, RewardCoupon.status == "active",
            RewardCoupon.required_days > 0).all():
        if c.progress_date == today_str:
            continue  # 今天已累计过
        # 本轮起点：优先 cycle_start_date（限期窗口券）；其次上次累计日；全新券从今天起算
        start_s = c.cycle_start_date or c.progress_date or today_str
        try:
            start = date.fromisoformat(str(start_s))
            if start > today:
                start = today
        except Exception:
            start = today
        # 硬性限期窗口：超过 required_within_days 仍未达成 → 本轮作废并重启窗口
        if (c.required_within_days or 0) > 0 and (today - start).days > c.required_within_days:
            c.progress_days = 0
            c.cycle_start_date = today_str
            start = today
        # 统计「本轮起点之后、今天之前」的缺卡/中断（旧缺卡不再拖累新本轮）
        miss = 0
        no_record_streak = 0
        interrupted = False
        d = start + timedelta(days=1)
        while d < today:
            day_rows = db.query(DailyTask).filter(
                DailyTask.user_id == user_id, DailyTask.task_date == d,
                DailyTask.task_type == "mandatory",
            ).all()
            if not day_rows:
                no_record_streak += 1
                if no_record_streak >= 2:
                    interrupted = True  # 连续 2 天以上无记录 → 视为中断
            else:
                no_record_streak = 0
                day_full = len(day_rows) >= 3 and all(r.status == "done" for r in day_rows)
                if not day_full:
                    # 检查是否用了补签卡
                    makeup = db.query(MakeupUsageLog).filter(
                        MakeupUsageLog.user_id == user_id,
                        MakeupUsageLog.target_date == d
                    ).count()
                    if not makeup:
                        miss += 1
            d += timedelta(days=1)
        if miss > 1 or interrupted:
            # 本轮作废：清零并从今天重新起算
            c.progress_days = 0
            c.cycle_start_date = today_str
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
