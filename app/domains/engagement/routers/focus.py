"""番茄专注钟（创意 22）：专注计时 + 记录 + 金币激励

孩子选择 10/15/25 分钟专注（纯前端倒计时），
完成后 POST /complete 记录并奖励金币 +2（防刷：同一天最多记录 8 次）。
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["focus"])

FOCUS_PAID = 2       # 每次完成专注奖励金币
FOCUS_DAILY_LIMIT = 8  # 每日记录上限（防刷，也保护孩子不过度用眼）


class FocusCompleteReq(BaseModel):
    user_id: str
    minutes: int  # 10/15/25


@router.post("/complete", summary="完成一次专注：记录 + 金币 +2")
def complete_focus(req: FocusCompleteReq, db: Session = Depends(get_db)):
    """完成一次专注：记录 + 金币 +2（防刷）。

    请求：{user_id, minutes=10/15/25}；无需家长密码。
    返回：{ok, granted(2 或 0), limited?, day_count}（limited=true 表示已达每日上限）。
    副作用：写 focus_sessions；每日记录上限 FOCUS_DAILY_LIMIT(8)（防刷且保护视力），超限仍记 0 币；
            记录成功后 PetService.grant_coins(+2, reason=专注完成)，发币失败不阻断。
    """
    from app.models.focus import FocusSession

    if req.minutes not in (10, 15, 25):
        raise HTTPException(400, "专注时长只能是 10/15/25 分钟")
    today = date.today()
    day_count = db.query(func.count()).filter(
        FocusSession.user_id == req.user_id,
        func.date(FocusSession.created_at) == str(today),
    ).scalar() or 0
    if day_count >= FOCUS_DAILY_LIMIT:
        return {"ok": True, "granted": 0, "limited": True, "day_count": day_count}
    db.add(FocusSession(user_id=req.user_id, minutes=req.minutes))
    try:
        from app.domains.engagement.contracts import PetService
        PetService.grant_coins(db, req.user_id, FOCUS_PAID, "专注完成")
    except Exception:
        pass
    db.commit()
    return {"ok": True, "granted": FOCUS_PAID, "day_count": day_count + 1}


@router.get("/today", summary="今日专注统计")
def focus_today(user_id: str = Query(...), db: Session = Depends(get_db)):
    """今日专注统计。查询参数：user_id；无需家长密码，只读。
    返回：{count, minutes, limit(每日上限)}。
    """
    from app.models.focus import FocusSession

    today = date.today()
    rows = db.query(FocusSession).filter(
        FocusSession.user_id == user_id,
        func.date(FocusSession.created_at) == str(today),
    ).all()
    total_min = sum(r.minutes for r in rows)
    return {"count": len(rows), "minutes": total_min, "limit": FOCUS_DAILY_LIMIT}


@router.get("/stats", summary="专注总统计（今日/本周/累计）")
def focus_stats(user_id: str = Query(...), db: Session = Depends(get_db)):
    """专注总统计（今日/本周/累计）。查询参数：user_id；无需家长密码，只读。
    返回：{today, week, total} 各含 {count, minutes}；本周以本周一为起点。
    """
    from app.models.focus import FocusSession

    today = date.today()
    week_start = today.fromordinal(today.toordinal() - today.weekday())
    rows = db.query(FocusSession).filter(FocusSession.user_id == user_id).all()
    today_min = sum(r.minutes for r in rows if r.created_at and r.created_at.date() == today)
    week_min = sum(r.minutes for r in rows if r.created_at and r.created_at.date() >= week_start)
    total_min = sum(r.minutes for r in rows)
    return {
        "today": {"count": sum(1 for r in rows if r.created_at and r.created_at.date() == today), "minutes": today_min},
        "week": {"count": sum(1 for r in rows if r.created_at and r.created_at.date() >= week_start), "minutes": week_min},
        "total": {"count": len(rows), "minutes": total_min},
    }
