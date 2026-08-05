"""简易用户系统 API

无需注册/密码，直接填写用户名即可使用。
登录时登记用户信息（用户名 + 常用年级/学科 + 活跃时间），
返回该用户的统计概览（连续学习天数等），前端 localStorage 记住用户名。
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog

router = APIRouter()


class UserLoginRequest(BaseModel):
    user_id: str
    grade: int = 6
    subject: str = "英语"


@router.post("/login", summary="用户登录登记（填用户名即用）")
def user_login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """登记用户（不存在则创建），返回用户档案与学习概览"""
    uid = req.user_id.strip()
    if not uid:
        from fastapi import HTTPException
        raise HTTPException(400, "用户名不能为空")

    user = db.query(User).filter(User.user_id == uid).first()
    is_new = False
    if not user:
        user = User(user_id=uid, grade=req.grade, subject=req.subject,
                    last_login_date=date.today())
        db.add(user)
        db.flush()
        is_new = True

    # 更新常用设置与活跃时间
    user.grade = req.grade
    user.subject = req.subject
    user.last_login_at = datetime.now()
    if user.last_login_date != date.today():
        user.last_login_date = date.today()
    db.commit()

    # 连续学习天数：词汇 + 古诗文 日志合并取最大
    streak = _streak(db, uid)

    return {
        "user_id": uid,
        "grade": user.grade,
        "subject": user.subject,
        "is_new": is_new,
        "streak_days": streak,
        "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else "",
        "message": "欢迎回来！" if not is_new else "欢迎加入，今天开始学习吧！",
    }


@router.get("/info", summary="获取用户信息")
def user_info(
    user_id: str,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == user_id.strip()).first()
    if not user:
        return None
    return {
        "user_id": user.user_id,
        "grade": user.grade,
        "subject": user.subject,
        "streak_days": _streak(db, user.user_id),
        "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else "",
        "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else "",
    }


def _streak(db: Session, user_id: str) -> int:
    """连续学习天数（合并词汇/古诗文日志，取两种日志里最大的连续天数）"""
    best = 0
    for model, count_col in ((VocabDailyLog, VocabDailyLog.new_words_learned),
                             (ClassicalDailyLog, ClassicalDailyLog.texts_learned)):
        logs = db.query(model).filter(
            model.user_id == user_id,
            count_col > 0,
        ).order_by(model.learn_date.desc()).all()
        if not logs:
            continue
        streak = 0
        check_date = date.today()
        if logs[0].learn_date < check_date:
            check_date = logs[0].learn_date
        log_dates = {log.learn_date for log in logs}
        while check_date in log_dates:
            streak += 1
            check_date -= timedelta(days=1)
        best = max(best, streak)
    return best
