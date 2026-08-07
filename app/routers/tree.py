"""成长树（创意 7）：从现有学习数据派生成长值，可视化成长阶段

零新表方案：成长值 = 各学习行为加权聚合，阶段按累计值划分。
设计原则（Notion 07）：可视化强、只和自己比、无需家长维护。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(tags=["tree"])

# 成长阶段（threshold: 名称 + emoji）
STAGES = [
    (0, "小种子", "🌱"),
    (20, "小幼苗", "🌿"),
    (60, "小树苗", "🪴"),
    (120, "青葱小树", "🌳"),
    (200, "茁壮大树", "🌳"),
    (300, "枝繁叶茂", "🌳"),
    (450, "开花啦", "🌸"),
    (600, "硕果累累", "🍎"),
    (800, "森林之王", "🌟"),
]


def _stage_of(score: int) -> dict:
    idx = 0
    for i, (th, _, _) in enumerate(STAGES):
        if score >= th:
            idx = i
        else:
            break
    th, name, emoji = STAGES[idx]
    next_th = STAGES[idx + 1][0] if idx + 1 < len(STAGES) else None
    return {
        "stage": idx,
        "name": name,
        "emoji": emoji,
        "next": next_th,
        "pct": min(100, round((score - th) / (next_th - th) * 100)) if next_th else 100,
        "maxed": next_th is None,
    }


def compute_tree_score(db: Session, user_id: str) -> int:
    """计算孩子成长值（供成长树接口与 AI 学习助手画像复用）"""
    from ..models.exam import AttemptAnswer, ExamAttempt, WrongRecord
    from ..models.study_error import StudyError
    from ..models.vocab import VocabProgress
    from ..models.classical import ClassicalProgress
    from ..models.daily_task import DailyTask
    from ..models.sprint4 import ChallengeRecord, TeachingRecord
    from ..models.mood import MoodCheckin

    def _count(model, col):
        return db.query(func.count(func.distinct(col))).filter(model.user_id == user_id).scalar() or 0

    def _count_where(model, cond):
        return db.query(func.count()).filter(model.user_id == user_id, cond).scalar() or 0

    parts = [
        ("attempts", _count(ExamAttempt, ExamAttempt.id), 2),
        ("correct", db.query(func.count()).select_from(AttemptAnswer).join(
            ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id
        ).filter(AttemptAnswer.is_correct == 1, ExamAttempt.user_id == user_id).scalar() or 0, 1),
        ("wrong", _count_where(WrongRecord, WrongRecord.is_mastered == 1)
         + _count_where(StudyError, StudyError.is_mastered == 1), 3),
        ("vocab", _count_where(VocabProgress, VocabProgress.status == "mastered"), 1),
        ("classical", _count_where(ClassicalProgress, ClassicalProgress.status == "mastered"), 2),
        ("tasks", _count_where(DailyTask, DailyTask.status == "done"), 1),
        ("challenge", _count(ChallengeRecord, ChallengeRecord.id), 2),
        ("teach", _count_where(TeachingRecord, TeachingRecord.recheck_status == "passed"), 3),
        ("mood", _count(MoodCheckin, MoodCheckin.id), 1),
    ]
    return sum(v * w for _, v, w in parts)


@router.get("", summary="成长树：成长值与阶段（从学习数据派生）")
def get_tree(user_id: str = Query(...), db: Session = Depends(get_db)):
    from ..models.exam import AttemptAnswer, ExamAttempt, WrongRecord
    from ..models.study_error import StudyError
    from ..models.vocab import VocabProgress
    from ..models.classical import ClassicalProgress
    from ..models.daily_task import DailyTask
    from ..models.sprint4 import ChallengeRecord, TeachingRecord
    from ..models.mood import MoodCheckin

    def _count(model, col):
        return db.query(func.count(func.distinct(col))).filter(model.user_id == user_id).scalar() or 0

    def _count_where(model, cond):
        return db.query(func.count()).filter(model.user_id == user_id, cond).scalar() or 0

    # 各部分原始量
    attempts = _count(ExamAttempt, ExamAttempt.id)
    correct_ans = db.query(func.count()).select_from(AttemptAnswer).join(
        ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id
    ).filter(AttemptAnswer.is_correct == 1, ExamAttempt.user_id == user_id).scalar() or 0
    exam_mastered = _count_where(WrongRecord, WrongRecord.is_mastered == 1)
    study_mastered = _count_where(StudyError, StudyError.is_mastered == 1)
    vocab_mastered = _count_where(VocabProgress, VocabProgress.status == "mastered")
    classical_mastered = _count_where(ClassicalProgress, ClassicalProgress.status == "mastered")
    tasks_done = _count_where(DailyTask, DailyTask.status == "done")
    challenges = _count(ChallengeRecord, ChallengeRecord.id)
    teach_passed = _count_where(TeachingRecord, TeachingRecord.recheck_status == "passed")
    moods = _count(MoodCheckin, MoodCheckin.id)

    parts = [
        {"key": "attempts", "label": "刷题次数", "value": attempts, "score": attempts * 2},
        {"key": "correct", "label": "答对题数", "value": correct_ans, "score": correct_ans},
        {"key": "wrong", "label": "错题掌握", "value": exam_mastered + study_mastered, "score": (exam_mastered + study_mastered) * 3},
        {"key": "vocab", "label": "单词掌握", "value": vocab_mastered, "score": vocab_mastered},
        {"key": "classical", "label": "古诗文掌握", "value": classical_mastered, "score": classical_mastered * 2},
        {"key": "tasks", "label": "任务完成", "value": tasks_done, "score": tasks_done},
        {"key": "challenge", "label": "挑战次数", "value": challenges, "score": challenges * 2},
        {"key": "teach", "label": "小老师讲清", "value": teach_passed, "score": teach_passed * 3},
        {"key": "mood", "label": "心情打卡", "value": moods, "score": moods},
    ]
    parts = [p for p in parts if p["value"] > 0]
    score = sum(p["score"] for p in parts)
    return {
        "user_id": user_id,
        "score": score,
        "stage": _stage_of(score),
        "parts": sorted(parts, key=lambda p: -p["score"]),
    }
