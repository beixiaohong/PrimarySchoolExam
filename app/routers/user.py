"""简易用户系统 API

无需注册/密码，直接填写用户名即可使用。
登录时登记用户名，年级在进入系统后选择。
"""
from datetime import date, datetime, timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog

logger = logging.getLogger(__name__)

router = APIRouter()


class UserLoginRequest(BaseModel):
    user_id: str
    grade: int = None
    subject: str = None


class GradeUpdateRequest(BaseModel):
    user_id: str
    grade: int


@router.post("/login", summary="用户登录登记（填用户名即用）")
def user_login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """登记用户（不存在则创建），返回用户档案与学习概览"""
    uid = req.user_id.strip()
    if not uid:
        raise HTTPException(400, "用户名不能为空")

    user = db.query(User).filter(User.user_id == uid).first()
    is_new = False
    if not user:
        user = User(user_id=uid, grade=req.grade or 6, subject=req.subject or "英语",
                    last_login_date=date.today())
        db.add(user)
        db.flush()
        is_new = True

    # 仅当调用方显式传了 grade/subject 时才覆盖（登录页不再传这两个字段）
    if req.grade is not None:
        user.grade = req.grade
    if req.subject is not None:
        user.subject = req.subject
    user.last_login_at = datetime.now()
    if user.last_login_date != date.today():
        user.last_login_date = date.today()
    db.commit()

    # 启动时检查是否需要自动升年级（每年9月1号）
    _auto_upgrade_grade(db)

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


@router.post("/grade", summary="更新用户年级")
def update_grade(req: GradeUpdateRequest, db: Session = Depends(get_db)):
    """家长或用户手动修改年级"""
    uid = req.user_id.strip()
    if not uid:
        raise HTTPException(400, "用户名不能为空")
    if not (1 <= req.grade <= 12):
        raise HTTPException(400, "年级范围无效（1-12）")
    user = db.query(User).filter(User.user_id == uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.grade = req.grade
    db.commit()
    return {"user_id": uid, "grade": user.grade}


def _auto_upgrade_grade(db: Session):
    """每年9月1号自动将所有用户年级 +1（上限9年级）"""
    today = date.today()
    if today.month == 9 and today.day == 1:
        users = db.query(User).filter(User.grade < 9).all()
        for u in users:
            u.grade = (u.grade or 6) + 1
        db.commit()
        if users:
            logger.info("9月1日自动升年级：升级了 %d 个用户", len(users))


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
