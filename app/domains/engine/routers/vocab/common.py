"""背单词路由 - 艾宾浩斯记忆曲线（shared：constants / helpers / schemas）

本文件只承载跨子模块共享的定义，不含任何路由。router 定义在包 __init__.py。
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.word import Word, WordBook
from app.models.vocab import VocabProgress, VocabDailyLog
from app.domains.engagement.contracts import TaskService
from app.services import semester as _semester
from app.schemas.vocab import (
    VocabWordOut,
    LearnRequest,
    ReviewRequest,
    VocabStatsOut,
    TodayTaskOut,
    VocabProgressOut,
)

# 艾宾浩斯记忆曲线复习间隔（天）
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30]
# 每天新学单词数
NEW_WORDS_PER_DAY = 20


def _get_grade_books(db: Session, grade: int, user_id: Optional[str] = None) -> List[int]:
    """获取指定年级的词库ID：默认只开当前学期，include_next 开启时预支下学期。

    教材版本（2026-08-20 新增）：用户为英语选择了教材版本时，新学选材只取该版本
    对应词书（word_books.textbook_id）；该版本无词书/未选择时回退全部（保证有词可学）。
    累计统计（_career_book_ids）不做版本过滤，切换版本不丢历史学习量。
    """
    semesters = [_semester.current_semester()]
    if user_id and TaskService.study_flags(db, user_id).get("include_next"):
        semesters.append(_semester.next_semester())

    books = db.query(WordBook).filter(
        WordBook.grade == grade,
        WordBook.semester.in_(semesters),
    ).all()
    if user_id:
        from app.domains.content.contracts import resolve_textbook_id
        tid = resolve_textbook_id(db, user_id, "英语", grade)
        if tid:
            version_books = db.query(WordBook).filter(
                WordBook.grade == grade,
                WordBook.semester.in_(semesters),
                WordBook.textbook_id == tid,
            ).all()
            if version_books:
                return [b.id for b in version_books]
    if not books:
        # 兜底：该年级当前学期无册（数据未就绪）时回退全量，避免无词可学
        books = db.query(WordBook).filter(WordBook.grade == grade).all()
    return [b.id for b in books]


def _career_book_ids(db: Session, grade: int, user_id: Optional[str] = None) -> List[int]:
    """整个学生生涯词库（累计统计用）：本年级及以下所有年级；
    当前年级只取不超过当前学期的册（下学期含上下两册），低年级含上下两册。
    实现「每学期把当前阶段词库加进来」——累计学习量不随学期切换而丢失，
    与古诗文模块（ClassicalText.grade <= grade）口径保持一致。"""
    cur = _semester.current_semester()
    books = db.query(WordBook).filter(
        WordBook.grade <= grade,
        or_(WordBook.grade < grade, WordBook.semester <= cur),
    ).all()
    ids = [b.id for b in books]
    if user_id and TaskService.study_flags(db, user_id).get("include_next"):
        # 预支下学期：把当前年级的下一学期册也纳入累计池
        nxt = _semester.next_semester()
        extra = db.query(WordBook.id).filter(
            WordBook.grade == grade, WordBook.semester == nxt
        ).all()
        ids += [r[0] for r in extra]
    if not ids:
        # 兜底：本年级及以下均无册（数据未就绪）时回退当前年级全量
        ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
    return ids


def _sync_unit_filter(db: Session, user_id: str, book_ids: List[int]):
    """课堂同步：sync_mode 开启时返回英语当前进度的 (book_id, unit)，否则 None"""
    if not TaskService.study_flags(db, user_id).get("sync_mode"):
        return None
    from app.models.middle import TeachingProgress
    prog = db.query(TeachingProgress).filter(
        TeachingProgress.user_id == user_id,
        TeachingProgress.subject == "英语",
    ).first()
    if not prog or not prog.book_id or not prog.chapter:
        return None
    if prog.book_id not in book_ids:
        return None
    return prog.book_id, prog.chapter


def _get_today_log(db: Session, user_id: str, today: date) -> VocabDailyLog:
    """获取或创建今日学习日志"""
    log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date == today
    ).first()
    if not log:
        log = VocabDailyLog(user_id=user_id, learn_date=today)
        db.add(log)
        db.commit()
        db.refresh(log)
    return log


def _calc_next_review(stage: int, from_date: date) -> date:
    """根据复习阶段计算下次复习日期"""
    if stage >= len(EBBINGHAUS_INTERVALS):
        # 已完成所有复习阶段，30天后复查
        return from_date + timedelta(days=30)
    return from_date + timedelta(days=EBBINGHAUS_INTERVALS[stage])


def _get_streak(db: Session, user_id: str) -> int:
    """计算连续学习天数"""
    logs = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.new_words_learned > 0
    ).order_by(VocabDailyLog.learn_date.desc()).all()

    if not logs:
        return 0

    streak = 0
    check_date = date.today()
    # 如果今天还没学，从昨天开始算
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date

    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)

    return streak


__all__ = [
    "EBBINGHAUS_INTERVALS",
    "NEW_WORDS_PER_DAY",
    "_get_grade_books",
    "_career_book_ids",
    "_sync_unit_filter",
    "_get_today_log",
    "_calc_next_review",
    "_get_streak",
    "VocabWordOut",
    "LearnRequest",
    "ReviewRequest",
    "VocabStatsOut",
    "TodayTaskOut",
    "VocabProgressOut",
]
