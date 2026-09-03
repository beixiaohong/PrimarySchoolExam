"""心情打卡：每日一次心情记录 + 7 天趋势 + 压力预警

表 mood_checkins（004 迁移已建）：user_id + check_date 唯一约束（每日一条，可覆盖）。
mood 取值：great/happy/ok/blue/sad；负面 = blue/sad。
连续 3 天及以上负面 → trend 返回 alert，前端（家长统计区）展示沟通建议卡。
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()

MOODS = ("great", "happy", "ok", "blue", "sad")
NEGATIVE = ("blue", "sad")
MOOD_LABELS = {
    "great": "超开心", "happy": "开心", "ok": "一般",
    "blue": "有点烦", "sad": "很难过",
}


class MoodCheckinReq(BaseModel):
    user_id: str
    mood: str
    note: str = ""


@router.post("/checkin", summary="心情打卡（当日可改，覆盖上次）")
def mood_checkin(req: MoodCheckinReq, db: Session = Depends(get_db)):
    """每日心情打卡（当日可重复修改，覆盖上次记录）。

    参数（Body）：user_id、mood（great/happy/ok/blue/sad）、note（最长 50 字）。
    返回：{date, mood, label, note}。mood 非法返回 400。
    副作用：upsert mood_checkins（user_id+check_date 唯一）；无需家长密码。
    """
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise HTTPException(400, "缺少 user_id")
    if req.mood not in MOODS:
        raise HTTPException(400, f"心情取值只能是 {MOODS}")
    note = (req.note or "").strip()[:50]

    from app.models.mood import MoodCheckin
    today = date.today()
    row = db.query(MoodCheckin).filter(
        MoodCheckin.user_id == user_id,
        MoodCheckin.check_date == today,
    ).first()
    if row:
        row.mood = req.mood
        row.note = note
    else:
        db.add(MoodCheckin(user_id=user_id, check_date=today, mood=req.mood, note=note))
    db.commit()
    return {"date": str(today), "mood": req.mood, "label": MOOD_LABELS.get(req.mood, req.mood), "note": note}


@router.get("/trend", summary="最近 7 天心情曲线 + 压力预警")
def mood_trend(user_id: str = Query(..., description="用户名"), db: Session = Depends(get_db)):
    """返回最近 7 天心情曲线，并在连续负面（blue/sad）≥3 天时给出压力预警。

    参数（Query）：user_id。
    返回：{days[7], alert|null, today_mood}。
    副作用：无（只读）。无需家长密码。
    """
    today = date.today()
    start = today - timedelta(days=6)

    from app.models.mood import MoodCheckin
    rows = db.query(MoodCheckin).filter(
        MoodCheckin.user_id == user_id,
        MoodCheckin.check_date >= start,
        MoodCheckin.check_date <= today,
    ).order_by(MoodCheckin.check_date.asc()).all()
    by_date = {r.check_date: r for r in rows}

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        r = by_date.get(d)
        days.append({
            "date": str(d),
            "weekday": "一二三四五六日"[d.weekday()],
            "mood": r.mood if r else "",
            "label": MOOD_LABELS.get(r.mood, "") if r else "",
            "note": r.note if r else "",
            "negative": bool(r and r.mood in NEGATIVE),
        })

    # 连续负面天数（含今天向前推）
    streak = 0
    for d in reversed(days):
        if d["negative"]:
            streak += 1
        else:
            break

    alert = None
    if streak >= 3:
        alert = {
            "streak": streak,
            "text": f"孩子已连续 {streak} 天心情不太好（最近一次：{days[-1]['label']}），建议找个轻松的时间和孩子聊聊",
        }

    return {"days": days, "alert": alert, "today_mood": days[-1]["mood"] if days else ""}
