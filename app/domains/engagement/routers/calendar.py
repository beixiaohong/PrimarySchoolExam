"""学习日历：聚合每日任务 / 专注 / 心情打卡，可视化坚持曲线 + 连续打卡天数

复用 engagement 域已有三张表（daily_tasks / focus_sessions / mood_checkins），
不新增表。连续打卡(streak) 与累计统计供前端「学习日历」页展示坚持成就。
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_task import DailyTask
from app.models.focus import FocusSession
from app.models.mood import MoodCheckin

router = APIRouter(tags=["calendar"])

DEFAULT_DAYS = 90
MAX_DAYS = 365


@router.get("", summary="学习日历：按日聚合任务/专注/心情打卡")
def study_calendar(
    user_id: str = Query(..., description="用户账号"),
    days: int = Query(DEFAULT_DAYS, ge=7, le=MAX_DAYS, description="回溯天数"),
    db: Session = Depends(get_db),
):
    """返回最近 days 天每天的学习印记，用于热力日历 + 连续打卡统计。

    - tasks_done：当日 status=done 的每日任务数
    - focus_minutes：当日专注分钟合计
    - mood：当日心情（若有打卡）
    - checked_in：当日有任一学习行为（任务完成 / 专注 / 心情打卡）
    """
    end = date.today()
    start = end - timedelta(days=days - 1)

    # 1) 每日任务完成数（按天分组，单条范围查询，避免逐日查库）
    done_rows = (
        db.query(DailyTask.task_date, func.count())
        .filter(DailyTask.user_id == user_id,
                DailyTask.task_date >= start,
                DailyTask.task_date <= end,
                DailyTask.status == "done")
        .group_by(DailyTask.task_date)
        .all()
    )
    tasks_done = {d.isoformat(): c for d, c in done_rows}

    # 2) 专注分钟（按天分组）
    focus_start = datetime(start.year, start.month, start.day)
    focus_end = datetime(end.year, end.month, end.day) + timedelta(days=1)
    focus_rows = (
        db.query(FocusSession)
        .filter(FocusSession.user_id == user_id,
                FocusSession.created_at >= focus_start,
                FocusSession.created_at < focus_end)
        .all()
    )
    focus_min = {}
    for r in focus_rows:
        if r.created_at:
            d = r.created_at.date().isoformat()
            focus_min[d] = focus_min.get(d, 0) + (r.minutes or 0)

    # 3) 心情打卡（每天取最新一条）
    mood_rows = (
        db.query(MoodCheckin)
        .filter(MoodCheckin.user_id == user_id,
                MoodCheckin.check_date >= start,
                MoodCheckin.check_date <= end)
        .order_by(MoodCheckin.check_date.asc(), MoodCheckin.id.desc())
        .all()
    )
    mood_map = {}
    for r in mood_rows:
        mood_map.setdefault(r.check_date.isoformat(), r.mood)

    # 组装每日
    days_out = []
    checked_set = set()
    for i in range(days):
        d = start + timedelta(days=i)
        ds = d.isoformat()
        td = tasks_done.get(ds, 0)
        fm = focus_min.get(ds, 0)
        mo = mood_map.get(ds)
        checked = td > 0 or fm > 0 or mo is not None
        if checked:
            checked_set.add(ds)
        days_out.append({
            "date": ds,
            "tasks_done": td,
            "focus_minutes": fm,
            "mood": mo,
            "checked_in": checked,
        })

    # 连续打卡：从今天往前数（今天没打卡则从昨天算，不中断历史连续）
    streak = 0
    cur = end
    if cur.isoformat() not in checked_set:
        cur = cur - timedelta(days=1)
    while cur.isoformat() in checked_set:
        streak += 1
        cur = cur - timedelta(days=1)

    return {
        "days": days_out,
        "streak": streak,
        "total_days": len(checked_set),
        "total_focus_minutes": sum(focus_min.values()),
        "total_tasks_done": sum(tasks_done.values()),
        "range": {"start": start.isoformat(), "end": end.isoformat()},
    }
