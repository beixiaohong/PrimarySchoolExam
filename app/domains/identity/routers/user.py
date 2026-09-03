"""简易用户系统 API

无需注册/密码，直接填写用户名即可使用。
登录时登记用户名，年级在进入系统后选择。
"""
from datetime import date, datetime, timedelta
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import ALLOW_NICKNAME_LOGIN
from app.database import get_db
from app.models.user import User
from app.models.vocab import VocabDailyLog
from app.models.classical import ClassicalDailyLog

logger = logging.getLogger(__name__)

router = APIRouter()


class UserLoginRequest(BaseModel):
    user_id: str
    grade: int = None
    subject: str = None


class GradeUpdateRequest(BaseModel):
    user_id: str
    grade: int


@router.post("/login", summary="用户登录登记（昵称快捷入口）")
def user_login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """登记用户（不存在则创建），返回用户档案与学习概览"""
    if not ALLOW_NICKNAME_LOGIN:
        raise HTTPException(403, "昵称登录已关闭，请使用邮箱/手机号账号登录")
    uid = req.user_id.strip()
    if not uid:
        raise HTTPException(400, "用户名不能为空")

    user = db.query(User).filter(User.user_id == uid).first()
    is_new = False
    now = datetime.now()
    if not user:
        # 新建时一次性写全登录时间，避免同事务 INSERT 后再 UPDATE（代理环境下不稳定）
        user = User(user_id=uid, grade=req.grade or 6, subject=req.subject or "英语",
                    auth_type="nickname", nickname=uid,
                    last_login_at=now, last_login_date=date.today())
        db.add(user)
        db.commit()
        is_new = True
    else:
        # 仅当调用方显式传了 grade/subject 时才覆盖（登录页不再传这两个字段）
        if req.grade is not None:
            user.grade = req.grade
        if req.subject is not None:
            user.subject = req.subject
        user.last_login_at = now
        if user.last_login_date != date.today():
            user.last_login_date = date.today()
        db.commit()

    # 启动时检查是否需要自动升年级（每年9月1号）；升级后返回 promoted 供前端弹窗
    prev_grade = user.grade
    _auto_upgrade_grade(db)
    promoted = (not is_new) and bool(prev_grade) and bool(user.grade) and user.grade > prev_grade

    # 连续学习天数：词汇 + 古诗文 日志合并取最大
    streak = _streak(db, uid)

    return {
        "user_id": uid,
        "grade": user.grade,
        "subject": user.subject,
        "is_new": is_new,
        "promoted": promoted,
        "prev_grade": prev_grade if promoted else None,
        "new_grade": user.grade if promoted else None,
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
    """获取用户基础信息（年级/学科/连续天数/创建与最近登录时间）。

    参数（Query）：user_id。
    返回：用户档案对象；用户不存在返回 null。
    副作用：无（只读）。无需家长密码。
    """
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


# ═══════════════════ 称号系统（成长积分制） ═══════════════════
#
# 旧版：称号只看「累计作答量」（做题+灭错+单词+古诗文，含复习），
#       复习量也能刷，导致很快到顶。
# 新版：称号由「成长积分(GP)」决定，GP = 基础学习 + 任务积分 + 成就计分，
#       且基础学习与任务积分【每天限额】，防止单日猛刷快速升级。
#
#   · 基础学习（每天封顶 BASE_CAP_PER_DAY）：仅统计"新学"动作，不含复习——
#       新学单词 +1/个、新学古诗文 +2/篇、做题答对 +1/题。
#   · 任务积分（每天封顶 TASK_CAP_PER_DAY）：每完成一个每日任务 +TASK_PTS。
#   · 成就计分：里程碑式一次性加分（各徽章解锁即得分），天然有上限，不与每日刷量挂钩。
#
# 称号阶梯按 GP 阈值划分，档位更多、级差更小，需长期稳定积累才能到顶。

# ── 成长积分参数 ──
# 「分数调整高一些」：单次动作分值上调，让孩子每次学习更有获得感；
# 但长线节奏由「每日上限」兜底——上限压住，避免单日猛刷、十年才到顶。
BASE_PTS_WORD = 2      # 每新学一个单词（+1）
BASE_PTS_TEXT = 3      # 每新学一篇古诗文（+1）
BASE_PTS_EXAM = 2      # 每答对一道题（+1）
BASE_CAP_PER_DAY = 4   # 基础学习：单日计入上限（≈ 1~2 个新学动作即封顶）

TASK_PTS = 10          # 每完成一个每日任务（+5）
TASK_CAP_PER_DAY = 4   # 任务积分：单日计入上限（≈ 1 个任务即封顶）

# 成就计分：徽章解锁即得分（一次性，总量有限，不与每日刷量挂钩）
ACHIEVEMENT_POINTS = {
    "master": 20,     # 错题克星（掌握错题 ≥20）
    "word": 20,       # 单词小达人（累计学单词 ≥100）
    "poem": 15,       # 诗词小状元（古诗文 ≥10）
    "streak": 15,     # 全勤达人（连续完成天 ≥7）
    "challenger": 10, # 挑战高手（单场最高答对 ≥10）
}

# 称号阶梯（GP 阈值，由高到低）—— 沿用原 15 档间距。
# 节奏校准：顶档 超级学霸(4500) 按「约十年到顶」设计。
#   单次动作分值已上调（见上方参数），但每日上限合计≈8 GP/天，
#   故即使「每天封顶」也需 4500/8≈560 个封顶日；
#   若按小学生实际约 50 个有效学习日/年（≈每周一次，含假期摊薄），
#   则 ≈ 560/50 ≈ 11 年；若全年高频使用则更快，符合「需长期积累」诉求。
TITLE_LADDER = [
    (4500, "超级学霸", "👑"),
    (3700, "鸿儒硕学", "🏛️"),
    (3000, "满腹经纶", "📜"),
    (2500, "学海扬帆", "⛵"),
    (2000, "博闻多识", "🌟"),
    (1600, "勤思学霸", "📚"),
    (1250, "睿智学童", "🔆"),
    (960, "知识探险家", "🧭"),
    (720, "思辨新锐", "💡"),
    (520, "笃学标兵", "🏅"),
    (350, "博学少年", "🎓"),
    (220, "进阶学子", "📖"),
    (120, "勤学小将", "⚔️"),
    (50, "求知小苗", "🌿"),
    (0, "学习萌新", "🌱"),
]


@router.get("/titles", summary="称号与徽章（按累计学习数据派生）")
def get_titles(user_id: str, db: Session = Depends(get_db)):
    """称号与徽章（成长积分制，纯派生只读计算）。

    称号由「成长积分(GP)」对照 TITLE_LADDER 阈值决定：
        GP = 基础学习(按天封顶,仅新学不含复习)
           + 任务积分(按天封顶,每完成一个每日任务)
           + 成就计分(徽章解锁一次性加分)
    —— 基础学习与任务积分均设每日上限，防止单日猛刷快速升级；
       复习量不再计入基础，避免靠刷题/复习堆量到顶。
    徽章含 5 项成就（见 ACHIEVEMENT_POINTS）。
    参数（Query）：user_id。
    返回：{main, next, total_answered(=GP,兼容), growth{base,task,achievement,...},
           badges[], stats{...}}。
    副作用：无（只读）。无需家长密码。
    """
    from app.models.exam import ExamAttempt, WrongRecord
    from app.models.study_error import StudyError
    from app.models.daily_task import DailyTask
    from app.models.sprint4 import ChallengeRecord

    total_exam = db.query(ExamAttempt).filter(ExamAttempt.user_id == user_id).all()
    study_errs = db.query(StudyError).filter(StudyError.user_id == user_id).all()

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
    done_tasks = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.status == "done").all()
    done_dates = {row.task_date for row in done_tasks}
    streak = 0
    d = date.today()
    while d in done_dates:
        streak += 1
        d -= timedelta(days=1)

    best = db.query(ChallengeRecord).filter(
        ChallengeRecord.user_id == user_id).all()
    challenge_best = max((r.correct for r in best), default=0)

    # ── 成长积分（GP）计算 ──
    # 1) 基础学习：按天聚合"新学"动作，单日封顶 BASE_CAP_PER_DAY（不含复习，避免刷复习升级）
    base_by_day = {}
    for r in vocab_learned:
        d = r.learn_date
        base_by_day[d] = base_by_day.get(d, 0) + (r.new_words_learned or 0) * BASE_PTS_WORD
    for r in classical_rows:
        d = r.learn_date
        base_by_day[d] = base_by_day.get(d, 0) + (r.texts_learned or 0) * BASE_PTS_TEXT
    for a in total_exam:
        d = (a.created_at or datetime.now()).date()
        base_by_day[d] = base_by_day.get(d, 0) + (a.correct or 0) * BASE_PTS_EXAM
    base_gp = sum(min(v, BASE_CAP_PER_DAY) for v in base_by_day.values())

    # 2) 任务积分：按天聚合已完成任务，单日封顶 TASK_CAP_PER_DAY
    task_by_day = {}
    for t in done_tasks:
        task_by_day[t.task_date] = task_by_day.get(t.task_date, 0) + TASK_PTS
    task_gp = sum(min(v, TASK_CAP_PER_DAY) for v in task_by_day.values())

    # 3) 成就计分：徽章解锁即得分（里程碑式一次性加分，总量有限）
    ach_gp = 0
    if mastered >= 20: ach_gp += ACHIEVEMENT_POINTS["master"]
    if words >= 100: ach_gp += ACHIEVEMENT_POINTS["word"]
    if texts >= 10: ach_gp += ACHIEVEMENT_POINTS["poem"]
    if streak >= 7: ach_gp += ACHIEVEMENT_POINTS["streak"]
    if challenge_best >= 10: ach_gp += ACHIEVEMENT_POINTS["challenger"]

    gp = base_gp + task_gp + ach_gp

    main = TITLE_LADDER[0]
    next_t = None
    for t in TITLE_LADDER:
        if gp >= t[0]:
            main = t
            break
    for t in reversed(TITLE_LADDER):
        if t[0] > gp:
            next_t = t
    if next_t:
        next_t = {"name": next_t[1], "icon": next_t[2],
                  "need": next_t[0] - gp, "total": next_t[0]}

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
        "total_answered": gp,   # 兼容旧字段，现表示成长积分(GP)
        "growth": {
            "total": gp,
            "base": base_gp,
            "task": task_gp,
            "achievement": ach_gp,
            "base_cap": BASE_CAP_PER_DAY,
            "task_cap": TASK_CAP_PER_DAY,
            "achievement_max": sum(ACHIEVEMENT_POINTS.values()),
        },
        "badges": badges,
        "stats": {"words": words, "texts": texts, "mastered": mastered,
                  "streak": streak, "challenge_best": challenge_best},
    }
