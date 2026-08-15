"""古诗文：学习统计"""
from datetime import date

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.classical import ClassicalText, ClassicalProgress, ClassicalDailyLog

from . import router
from .common import _get_streak


@router.get("/stats", summary="古诗文学习统计")
def get_stats(
    user_id: str = Query(...),
    grade: int = Query(6),
    db: Session = Depends(get_db),
):
    """获取古诗文学习统计：总篇数、已学数、已掌握数、待复习数、今日新学/复习数、连续天数。

    参数（Query）：user_id、grade（统计该年级及以下）。返回：统计字典。
    副作用：只读。无需家长密码。
    """
    today = date.today()
    total = db.query(ClassicalText).filter(ClassicalText.grade <= grade).count()
    all_progress = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.text_id.in_(
            db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        )
    ).all()

    learned = len(all_progress)
    mastered = sum(1 for p in all_progress if p.status == "mastered")
    due_today = sum(
        1 for p in all_progress
        if p.status == "learning" and p.next_review_date and p.next_review_date <= today
    )

    today_log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.learn_date == today,
    ).first()

    return {
        "total": total,
        "learned": learned,
        "mastered": mastered,
        "learning": learned - mastered,
        "due_today": due_today,
        "new_today": today_log.texts_learned if today_log else 0,
        "review_today": today_log.texts_reviewed if today_log else 0,
        "streak_days": _get_streak(db, user_id),
    }


__all__ = [
    "get_stats",
]
