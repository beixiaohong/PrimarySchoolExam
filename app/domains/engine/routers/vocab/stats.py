"""背单词：统计 / 进度 / 历史"""
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.word import Word, WordBook
from app.models.vocab import VocabProgress, VocabDailyLog

from . import router
from .common import (
    _career_book_ids,
    _get_streak,
    VocabStatsOut,
    VocabProgressOut,
)


@router.get("/stats", response_model=VocabStatsOut, summary="用户词汇学习统计")
def get_vocab_stats(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    db: Session = Depends(get_db),
):
    """获取用户词汇学习统计（累计口径：整个学生生涯）"""
    today = date.today()
    book_ids = _career_book_ids(db, grade, user_id)

    if not book_ids:
        return VocabStatsOut(
            total_words=0, learned_count=0, mastered_count=0, learning_count=0,
            new_today=0, review_today=0, due_today=0, streak_days=0, total_learned_all_time=0,
        )

    word_ids_subq = db.query(Word.id).filter(Word.book_id.in_(book_ids))

    total_words = db.query(Word).filter(Word.book_id.in_(book_ids)).count()

    all_progress = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.word_id.in_(word_ids_subq)
    ).all()

    learned_count = len(all_progress)
    mastered_count = sum(1 for p in all_progress if p.status == "mastered")
    learning_count = learned_count - mastered_count

    # 今日数据
    today_log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date == today
    ).first()
    new_today = today_log.new_words_learned if today_log else 0
    review_today = today_log.words_reviewed if today_log else 0

    # 今日待复习
    due_today = sum(
        1 for p in all_progress
        if p.status == "learning" and p.next_review_date and p.next_review_date <= today
    )

    streak = _get_streak(db, user_id)

    # 累计学习总数（不限年级）
    total_all_time = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id
    ).count()

    return VocabStatsOut(
        total_words=total_words,
        learned_count=learned_count,
        mastered_count=mastered_count,
        learning_count=learning_count,
        new_today=new_today,
        review_today=review_today,
        due_today=due_today,
        streak_days=streak,
        total_learned_all_time=total_all_time,
    )


@router.get("/progress", summary="查看单词学习进度列表")
def get_progress(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    status: Optional[str] = Query(None, description="过滤状态: learning/mastered"),
    db: Session = Depends(get_db),
):
    """查看用户所有单词的学习进度（累计口径：整个学生生涯）"""
    book_ids = _career_book_ids(db, grade, user_id)
    if not book_ids:
        return []

    query = db.query(VocabProgress, Word).join(
        Word, VocabProgress.word_id == Word.id
    ).filter(
        VocabProgress.user_id == user_id,
        Word.book_id.in_(book_ids),
    )

    if status:
        query = query.filter(VocabProgress.status == status)

    query = query.order_by(VocabProgress.updated_at.desc())
    rows = query.all()

    return [
        VocabProgressOut(
            word_id=prog.word_id,
            word=w.word,
            meaning=w.meaning,
            status=prog.status,
            review_stage=prog.review_stage,
            next_review_date=prog.next_review_date,
            correct_count=prog.correct_count,
            wrong_count=prog.wrong_count,
            total_reviews=prog.total_reviews,
        )
        for prog, w in rows
    ]


@router.get("/history", summary="查看历史学习日志")
def get_history(
    user_id: str = Query(..., description="用户名"),
    days: int = Query(30, description="查询天数"),
    db: Session = Depends(get_db),
):
    """查看最近N天的学习日志"""
    start_date = date.today() - timedelta(days=days)
    logs = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date >= start_date,
    ).order_by(VocabDailyLog.learn_date.desc()).all()

    return [
        {
            "date": str(log.learn_date),
            "new_words": log.new_words_learned,
            "reviewed": log.words_reviewed,
            "correct": log.correct_count,
            "wrong": log.wrong_count,
        }
        for log in logs
    ]


__all__ = [
    "get_vocab_stats",
    "get_progress",
    "get_history",
]
