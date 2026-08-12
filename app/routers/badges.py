"""成就徽章墙（创意 8）：从学习数据派生判定，首次达成自动授予

规则硬编码于此（Badges 定义 + 条件函数），badge_earned 表只记授予时间。
GET /api/badges 即扫描全部条件并授予新徽章，返回徽章墙全量数据。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(tags=["badges"])

# 徽章定义：code, emoji, name, desc
BADGES = [
    {"code": "first_exam", "emoji": "🎯", "name": "初出茅庐", "desc": "完成第一次刷题"},
    {"code": "exam_10", "emoji": "💯", "name": "刷题达人", "desc": "累计刷题 10 次"},
    {"code": "exam_50", "emoji": "🚀", "name": "刷题狂魔", "desc": "累计刷题 50 次"},
    {"code": "perfect", "emoji": "🔥", "name": "满分学霸", "desc": "一次考试拿到 100 分"},
    {"code": "wrong_5", "emoji": "📚", "name": "错题克星", "desc": "掌握 5 道错题"},
    {"code": "wrong_20", "emoji": "🏆", "name": "错题终结者", "desc": "掌握 20 道错题"},
    {"code": "streak_7", "emoji": "🔥", "name": "一周全勤", "desc": "连续学习 7 天"},
    {"code": "streak_30", "emoji": "⭐", "name": "月度坚持", "desc": "连续学习 30 天"},
    {"code": "vocab_50", "emoji": "📖", "name": "单词之星", "desc": "掌握 50 个单词"},
    {"code": "classical_10", "emoji": "📜", "name": "诗词达人", "desc": "掌握 10 篇古诗文"},
    {"code": "teach_1", "emoji": "🎓", "name": "小老师出道", "desc": "把一道题给家长讲清楚"},
    {"code": "challenge_10", "emoji": "⚡", "name": "挑战先锋", "desc": "参加 10 次挑战赛"},
    {"code": "mood_7", "emoji": "💖", "name": "心情晴雨表", "desc": "打卡心情 7 天"},
    {"code": "coin_100", "emoji": "🪙", "name": "小金库", "desc": "累计赚到 100 金币"},
    {"code": "tree_300", "emoji": "🌳", "name": "参天大树", "desc": "成长值达到 300"},
]


def _metrics(db: Session, user_id: str) -> dict:
    """一次扫描所有需要的统计数据"""
    from ..models.exam import AttemptAnswer, ExamAttempt, WrongRecord
    from ..models.study_error import StudyError
    from ..models.vocab import VocabProgress
    from ..models.classical import ClassicalProgress
    from ..models.sprint4 import ChallengeRecord, TeachingRecord
    from ..models.mood import MoodCheckin
    from ..models.pet import CoinLedger
    from ..models.daily_task import DailyTask

    def _cnt(model, cond=None):
        q = db.query(func.count()).filter(model.user_id == user_id)
        if cond is not None:
            q = q.filter(cond)
        return q.scalar() or 0

    def _max_score():
        return db.query(func.max(ExamAttempt.score)).filter(ExamAttempt.user_id == user_id).scalar() or 0

    def _streak():
        """连续学习天数：从每日任务完成日期向后推算连续"""
        dates = {r[0] for r in db.query(DailyTask.task_date).filter(
            DailyTask.user_id == user_id, DailyTask.status == "done").all()}
        from datetime import date, timedelta
        d = date.today()
        n = 0
        while str(d) in dates:
            n += 1
            d -= timedelta(days=1)
        return n

    return {
        "attempts": _cnt(ExamAttempt),
        "max_score": _max_score(),
        "wrong_mastered": _cnt(WrongRecord, WrongRecord.is_mastered == 1) + _cnt(StudyError, StudyError.is_mastered == 1),
        "streak": _streak(),
        "vocab_mastered": _cnt(VocabProgress, VocabProgress.status == "mastered"),
        "classical_mastered": _cnt(ClassicalProgress, ClassicalProgress.status == "mastered"),
        "teach_passed": _cnt(TeachingRecord, TeachingRecord.recheck_status == "passed"),
        "challenges": _cnt(ChallengeRecord),
        "moods": _cnt(MoodCheckin),
        "coins_in": db.query(func.coalesce(func.sum(CoinLedger.amount), 0)).filter(
            CoinLedger.user_id == user_id, CoinLedger.amount > 0).scalar() or 0,
        "tree_score": _tree_score(db, user_id),
    }


def _tree_score(db: Session, user_id: str) -> int:
    """与 tree.py 同口径的成长值（简化复制，避免循环依赖）"""
    from ..models.exam import AttemptAnswer, ExamAttempt, WrongRecord
    from ..models.study_error import StudyError
    from ..models.vocab import VocabProgress
    from ..models.classical import ClassicalProgress
    from ..models.daily_task import DailyTask
    from ..models.sprint4 import ChallengeRecord, TeachingRecord
    from ..models.mood import MoodCheckin

    attempts = db.query(func.count(func.distinct(ExamAttempt.id))).filter(ExamAttempt.user_id == user_id).scalar() or 0
    correct_ans = db.query(func.count()).select_from(AttemptAnswer).join(ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id).filter(
        AttemptAnswer.is_correct == 1, ExamAttempt.user_id == user_id).scalar() or 0
    wrong_m = db.query(func.count()).filter(WrongRecord.user_id == user_id, WrongRecord.is_mastered == 1).scalar() or 0
    study_m = db.query(func.count()).filter(StudyError.user_id == user_id, StudyError.is_mastered == 1).scalar() or 0
    vocab_m = db.query(func.count()).filter(VocabProgress.user_id == user_id, VocabProgress.status == "mastered").scalar() or 0
    cls_m = db.query(func.count()).filter(ClassicalProgress.user_id == user_id, ClassicalProgress.status == "mastered").scalar() or 0
    tasks_done = db.query(func.count()).filter(DailyTask.user_id == user_id, DailyTask.status == "done").scalar() or 0
    chal = db.query(func.count(func.distinct(ChallengeRecord.id))).filter(ChallengeRecord.user_id == user_id).scalar() or 0
    teach_p = db.query(func.count()).filter(TeachingRecord.user_id == user_id, TeachingRecord.recheck_status == "passed").scalar() or 0
    mood = db.query(func.count(func.distinct(MoodCheckin.id))).filter(MoodCheckin.user_id == user_id).scalar() or 0
    return (attempts * 2 + correct_ans + (wrong_m + study_m) * 3 + vocab_m
            + cls_m * 2 + tasks_done + chal * 2 + teach_p * 3 + mood)


def _check(code: str, m: dict) -> bool:
    return {
        "first_exam": m["attempts"] >= 1,
        "exam_10": m["attempts"] >= 10,
        "exam_50": m["attempts"] >= 50,
        "perfect": m["max_score"] >= 100,
        "wrong_5": m["wrong_mastered"] >= 5,
        "wrong_20": m["wrong_mastered"] >= 20,
        "streak_7": m["streak"] >= 7,
        "streak_30": m["streak"] >= 30,
        "vocab_50": m["vocab_mastered"] >= 50,
        "classical_10": m["classical_mastered"] >= 10,
        "teach_1": m["teach_passed"] >= 1,
        "challenge_10": m["challenges"] >= 10,
        "mood_7": m["moods"] >= 7,
        "coin_100": m["coins_in"] >= 100,
        "tree_300": m["tree_score"] >= 300,
    }.get(code, False)


@router.get("", summary="成就徽章墙：扫描并授予新徽章，返回全部徽章状态")
def get_badges(user_id: str = Query(...), db: Session = Depends(get_db)):
    """成就徽章墙：扫描并授予新徽章，返回全部徽章状态。

    查询参数：user_id；无需家长密码。
    返回：{total, earned(已得数), newly(本次新解锁 code 列表), items:[{code,emoji,name,desc,earned,earned_at}]}。
    副作用：一次性统计学习数据，对首次达成阈值的徽章新增 badge_earned 记录并落库（阈值见 _check）。
    """
    from ..models.badge import BadgeEarned

    m = _metrics(db, user_id)
    earned_map = {b.badge_code: b.earned_at for b in db.query(BadgeEarned).filter(
        BadgeEarned.user_id == user_id).all()}

    newly = []
    for b in BADGES:
        code = b["code"]
        if code in earned_map:
            continue
        if _check(code, m):
            db.add(BadgeEarned(user_id=user_id, badge_code=code))
            earned_map[code] = datetime.now()
            newly.append(code)
    if newly:
        db.commit()

    items = [{
        **b,
        "earned": b["code"] in earned_map,
        "earned_at": earned_map[b["code"]].strftime("%Y-%m-%d") if b["code"] in earned_map else None,
    } for b in BADGES]
    earned_count = sum(1 for i in items if i["earned"])
    return {"total": len(items), "earned": earned_count, "newly": newly, "items": items}
