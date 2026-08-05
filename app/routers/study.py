"""学习模块错题 + 今日任务汇总路由

错题打通：语法练习、古诗文默写等学习模块答错的题统一记入 study_errors，
与试卷错题（WrongRecord）一起在"错题本"中展示复习。

今日任务：汇总背单词/古诗文/语法/错题四个模块的待办数量，供首页使用。
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.study_error import StudyError
from ..models.exam import WrongRecord, Question
from ..models.vocab import VocabProgress, VocabDailyLog
from ..models.classical import ClassicalProgress, ClassicalDailyLog
from ..models.word import Word, WordBook
from ..models.classical import ClassicalText

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════

class StudyErrorItem(BaseModel):
    source_type: str  # grammar / classical
    source_id: int = 0
    module_name: str = ""
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    explanation: str = ""


class StudyErrorRecordRequest(BaseModel):
    user_id: str
    items: List[StudyErrorItem]


class StudyErrorMasterRequest(BaseModel):
    user_id: str
    error_id: int


# ═══════════════════════════════════════════════════════════
# 学习错题记录
# ═══════════════════════════════════════════════════════════

@router.post("/errors", summary="记录学习错题（批量，自动去重累计）")
def record_study_errors(req: StudyErrorRecordRequest, db: Session = Depends(get_db)):
    """记录学习模块错题。

    同一用户 + 来源 + 题目标识只保留一条记录，重复答错累计 error_count。
    """
    if not req.items:
        return {"recorded": 0}

    recorded = 0
    for item in req.items:
        if not item.question or not item.correct_answer:
            continue

        existing = db.query(StudyError).filter(
            StudyError.user_id == req.user_id,
            StudyError.source_type == item.source_type,
            StudyError.source_id == item.source_id,
        ).first()

        if existing:
            # 已掌握后再次答错：重新激活
            existing.is_mastered = False
            existing.mastered_at = None
            existing.error_count += 1
            existing.user_answer = item.user_answer
            existing.question = item.question
            existing.correct_answer = item.correct_answer
            existing.explanation = item.explanation
            if item.module_name:
                existing.module_name = item.module_name
            existing.wrong_at = date.today()
        else:
            db.add(StudyError(
                user_id=req.user_id,
                source_type=item.source_type,
                source_id=item.source_id,
                module_name=item.module_name,
                question=item.question,
                user_answer=item.user_answer,
                correct_answer=item.correct_answer,
                explanation=item.explanation,
                error_count=1,
                wrong_at=date.today(),
            ))
        recorded += 1

    db.commit()
    return {"recorded": recorded}


@router.get("/errors", summary="查询学习错题列表")
def list_study_errors(
    user_id: str = Query(..., description="用户名"),
    source_type: Optional[str] = Query(None, description="过滤来源: grammar/classical"),
    only_pending: bool = Query(False, description="只看未掌握"),
    db: Session = Depends(get_db),
):
    q = db.query(StudyError).filter(StudyError.user_id == user_id)
    if source_type:
        q = q.filter(StudyError.source_type == source_type)
    if only_pending:
        q = q.filter(StudyError.is_mastered == False)  # noqa: E712
    errors = q.order_by(StudyError.wrong_at.desc(), StudyError.id.desc()).all()

    return [
        {
            "id": e.id,
            "source_type": e.source_type,
            "module_name": e.module_name or ("语法练习" if e.source_type == "grammar" else "古诗文默写"),
            "question": e.question,
            "user_answer": e.user_answer,
            "correct_answer": e.correct_answer,
            "explanation": e.explanation,
            "error_count": e.error_count,
            "is_mastered": e.is_mastered,
            "wrong_at": str(e.wrong_at) if e.wrong_at else "",
        }
        for e in errors
    ]


@router.post("/errors/master", summary="标记学习错题已掌握")
def mark_study_error_mastered(req: StudyErrorMasterRequest, db: Session = Depends(get_db)):
    error = db.query(StudyError).filter(
        StudyError.id == req.error_id,
        StudyError.user_id == req.user_id,
    ).first()
    if not error:
        raise HTTPException(404, "错题记录不存在")
    error.is_mastered = True
    error.mastered_at = date.today()
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 今日任务汇总（首页）
# ═══════════════════════════════════════════════════════════

@router.get("/dashboard/today", summary="今日学习任务汇总")
def get_dashboard_today(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    subject: str = Query("英语", description="学科：数学/英语/语文"),
    db: Session = Depends(get_db),
):
    """汇总今日所有模块待办：背单词、古诗文、语法、错题（按学科归属过滤）

    学科归属：英语=背单词+语法练习，语文=古诗文，数学=无学习模块
    """
    today = date.today()

    # ── 背单词（仅英语科目展示） ──
    vocab = {"new_words": 0, "review_words": 0, "due_today": 0,
             "streak_days": 0, "learned": 0, "total": 0}
    if subject == "英语":
        book_ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
        if book_ids:
            word_ids_subq = db.query(Word.id).filter(Word.book_id.in_(book_ids))
            vocab["total"] = db.query(Word).filter(Word.book_id.in_(book_ids)).count()
            all_progress = db.query(VocabProgress).filter(
                VocabProgress.user_id == user_id,
                VocabProgress.word_id.in_(word_ids_subq),
            ).all()
            vocab["learned"] = len(all_progress)
            vocab["due_today"] = sum(
                1 for p in all_progress
                if p.status == "learning" and p.next_review_date and p.next_review_date <= today
            )
            today_log = db.query(VocabDailyLog).filter(
                VocabDailyLog.user_id == user_id,
                VocabDailyLog.learn_date == today,
            ).first()
            vocab["new_words"] = max(0, 10 - (today_log.new_words_learned if today_log else 0))
            vocab["review_words"] = vocab["due_today"]
            vocab["streak_days"] = _vocab_streak(db, user_id)

    # ── 古诗文（仅语文学科展示） ──
    classical = {"new_texts": 0, "review_texts": 0, "due_today": 0,
                 "streak_days": 0, "learned": 0, "total": 0}
    if subject == "语文":
        text_ids_subq = db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        classical["total"] = db.query(ClassicalText).filter(ClassicalText.grade <= grade).count()
        c_progress = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == user_id,
            ClassicalProgress.text_id.in_(text_ids_subq),
        ).all()
        classical["learned"] = len(c_progress)
        classical["due_today"] = sum(
            1 for p in c_progress
            if p.status == "learning" and p.next_review_date and p.next_review_date <= today
        )
        today_log = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id,
            ClassicalDailyLog.learn_date == today,
        ).first()
        new_done_today = today_log.texts_learned if today_log else 0
        classical["new_texts"] = max(0, 2 - new_done_today)
        classical["review_texts"] = classical["due_today"]
        classical["streak_days"] = _classical_streak(db, user_id)

    # ── 语法（仅英语科目展示） ──
    from ..models.grammar import GrammarExercise
    grammar = {"total_exercises": 0, "recent_wrong": 0}
    if subject == "英语":
        grammar = {
            "total_exercises": db.query(GrammarExercise).filter(
                GrammarExercise.grade <= grade
            ).count(),
            "recent_wrong": db.query(StudyError).filter(
                StudyError.user_id == user_id,
                StudyError.source_type == "grammar",
                StudyError.is_mastered == False,  # noqa: E712
            ).count(),
        }

    # ── 错题（按学科归属过滤） ──
    if subject == "英语":
        study_source = StudyError.source_type == "grammar"
    elif subject == "语文":
        study_source = StudyError.source_type == "classical"
    else:
        study_source = StudyError.source_type.in_([])  # 数学无学习错题
    wrong = {
        "exam_pending": db.query(WrongRecord).join(
            Question, WrongRecord.question_id == Question.id
        ).filter(
            WrongRecord.user_id == user_id,
            WrongRecord.is_mastered == False,  # noqa: E712
            Question.subject == subject,
        ).count(),
        "study_pending": db.query(StudyError).filter(
            StudyError.user_id == user_id,
            StudyError.is_mastered == False,  # noqa: E712
            study_source,
        ).count(),
    }

    total_todo = (
        wrong["exam_pending"] + wrong["study_pending"]
        + (vocab["new_words"] + vocab["review_words"] if subject == "英语" else 0)
        + (classical["new_texts"] + classical["review_texts"] if subject == "语文" else 0)
    )

    return {
        "date": str(today),
        "total_todo": total_todo,
        "vocab": vocab,
        "classical": classical,
        "grammar": grammar,
        "wrong": wrong,
    }


def _vocab_streak(db: Session, user_id: str) -> int:
    """连续学习天数（与 vocab 模块口径一致）"""
    logs = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.new_words_learned > 0,
    ).order_by(VocabDailyLog.learn_date.desc()).all()
    if not logs:
        return 0
    streak = 0
    check_date = date.today()
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date
    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


def _classical_streak(db: Session, user_id: str) -> int:
    """古诗文连续学习天数"""
    logs = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.texts_learned > 0,
    ).order_by(ClassicalDailyLog.learn_date.desc()).all()
    if not logs:
        return 0
    streak = 0
    check_date = date.today()
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date
    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak
