"""今日任务汇总（首页，全学科聚合）相关端点与辅助函数"""
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from . import router
from app.database import get_db
from app.models.study_error import StudyError
from app.models.exam import WrongRecord, Question, ExamAttempt
from app.models.vocab import VocabProgress, VocabDailyLog
from app.models.classical import ClassicalProgress, ClassicalDailyLog
from app.models.word import Word, WordBook
from app.models.classical import ClassicalText


@router.get("/dashboard/today", summary="今日学习任务汇总（全学科聚合）")
def get_dashboard_today(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    subject: str = Query("英语", description="学科（兼容旧参数，用于返回单科视图）"),
    db: Session = Depends(get_db),
):
    """汇总今日所有模块待办，按学科聚合返回。

    subjects 字段包含 数学/英语/语文 三科各自的待办（今日首页一次拉取全部）；
    total_todo 为全部学科合计；
    vocab/classical/grammar/wrong 为兼容旧前端字段（按 subject 参数返回对应学科）。
    """
    today = date.today()
    subjects = {}
    total = 0
    for subj in ("英语", "数学", "语文"):
        task = _build_subject_task(db, user_id, grade, subj, today)
        subjects[subj] = task
        total += task["total_todo"]

    cur = subjects.get(subject, subjects["英语"])
    return {
        "date": str(today),
        "total_todo": total,
        "subjects": subjects,
        # ── 兼容旧字段 ──
        "vocab": cur["vocab"],
        "classical": cur["classical"],
        "grammar": cur["grammar"],
        "wrong": cur["wrong"],
    }


def _build_subject_task(db: Session, user_id: str, grade: int, subject: str, today: date) -> dict:
    """计算单个学科的今日任务

    学科归属：英语=背单词+语法练习，语文=古诗文，数学=无学习模块
    """
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
            # 不限每日轮数：展示每轮新学额度（家长配置）
            from app.domains.engagement.contracts import TaskService
            vocab["new_words"] = TaskService.daily_quota(db, user_id, "daily_new_words")
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
        # 不限每日轮数：展示每轮新背额度（家长配置）
        from app.domains.engagement.contracts import TaskService
        classical["new_texts"] = TaskService.daily_quota(db, user_id, "daily_new_texts")
        classical["review_texts"] = classical["due_today"]
        classical["streak_days"] = _classical_streak(db, user_id)

    # ── 语法（仅英语科目展示） ──
    from app.models.grammar import GrammarExercise
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
        study_source = StudyError.source_type.in_(["grammar", "vocab"])
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
        "total_todo": total_todo,
        "vocab": vocab,
        "classical": classical,
        "grammar": grammar,
        "wrong": wrong,
    }


def _vocab_streak(db: Session, user_id: str) -> int:
    """连续学习天数（与 vocab 模块口径一致）

    优化：仅取去重后的 learn_date 一列（避免把每日日志全行拉回 Python），
    再在日期集合上计算连续天数。配合 ix_vocab_daily_log_user_date 索引。
    """
    rows = db.query(VocabDailyLog.learn_date).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.new_words_learned > 0,
    ).distinct().all()
    if not rows:
        return 0
    log_dates = {d for (d,) in rows}
    streak = 0
    check_date = date.today()
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


def _classical_streak(db: Session, user_id: str) -> int:
    """古诗文连续学习天数

    优化：同 _vocab_streak，仅取去重 learn_date；配合
    ix_classical_daily_log_user_date 索引。
    """
    rows = db.query(ClassicalDailyLog.learn_date).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.texts_learned > 0,
    ).distinct().all()
    if not rows:
        return 0
    log_dates = {d for (d,) in rows}
    streak = 0
    check_date = date.today()
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


__all__ = ["get_dashboard_today", "_build_subject_task", "_vocab_streak", "_classical_streak"]
