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


# ═══════════════════ 称号系统（Sprint 4，纯派生计算） ═══════════════════

TITLE_LADDER = [
    (1000, "超级学霸", "👑"),
    (500, "知识探险家", "🧭"),
    (200, "学霸学徒", "📚"),
    (50, "刷题小能手", "✏️"),
    (10, "答题小新星", "⭐"),
    (0, "学习萌新", "🌱"),
]


@router.get("/titles", summary="称号与徽章（按累计学习数据派生）")
def get_titles(user_id: str, db: Session = Depends(get_db)):
    from ..models.exam import ExamAttempt, WrongRecord
    from ..models.study_error import StudyError
    from ..models.daily_task import DailyTask
    from ..models.sprint4 import ChallengeRecord

    total_exam = db.query(ExamAttempt).filter(ExamAttempt.user_id == user_id).all()
    answered_exam = sum(a.total or 0 for a in total_exam)
    study_errs = db.query(StudyError).filter(StudyError.user_id == user_id).all()
    answered_study = sum(e.error_count or 0 for e in study_errs)

    vocab_learned = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id).all()
    words = sum(r.new_words_learned or 0 for r in vocab_learned)

    classical_rows = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id).all()
    texts = sum((r.texts_learned or 0) + (r.texts_reviewed or 0) for r in classical_rows)

    mastered = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
        WrongRecord.is_mastered.is_(True)).count() + db.query(StudyError).filter(
        StudyError.user_id == user_id, StudyError.is_mastered.is_(True)).count()

    # 全勤连续天数（含今天，以三科全 done 的天数为连续单位）
    done_dates = set()
    for row in db.query(DailyTask).filter(
            DailyTask.user_id == user_id, DailyTask.status == "done").all():
        done_dates.add(row.task_date)
    streak = 0
    d = date.today()
    while d in done_dates:
        streak += 1
        d -= timedelta(days=1)

    best = db.query(ChallengeRecord).filter(
        ChallengeRecord.user_id == user_id).all()
    challenge_best = max((r.correct for r in best), default=0)

    total_answered = answered_exam + answered_study + words + texts
    main = TITLE_LADDER[0]
    next_t = None
    for t in TITLE_LADDER:
        if total_answered >= t[0]:
            main = t
            break
    for t in reversed(TITLE_LADDER):
        if t[0] > total_answered:
            next_t = t
    if next_t:
        next_t = {"name": next_t[1], "icon": next_t[2],
                  "need": next_t[0] - total_answered, "total": next_t[0]}

    badges = [
        {"code": "master", "name": "错题克星", "icon": "📕",
         "unlocked": mastered >= 20, "progress": mastered, "target": 20},
        {"code": "word", "name": "单词小达人", "icon": "🔤",
         "unlocked": words >= 100, "progress": words, "target": 100},
        {"code": "poem", "name": "诗词小状元", "icon": "📜",
         "unlocked": texts >= 10, "progress": texts, "target": 10},
        {"code": "streak", "name": "全勤达人", "icon": "🔥",
         "unlocked": streak >= 7, "progress": streak, "target": 7},
        {"code": "challenger", "name": "挑战高手", "icon": "⚡",
         "unlocked": challenge_best >= 10, "progress": challenge_best, "target": 10},
    ]
    return {
        "main": {"name": main[1], "icon": main[2]},
        "next": next_t,
        "total_answered": total_answered,
        "badges": badges,
        "stats": {"words": words, "texts": texts, "mastered": mastered,
                  "streak": streak, "challenge_best": challenge_best},
    }
