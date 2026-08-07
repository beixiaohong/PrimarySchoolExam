"""背单词路由 - 艾宾浩斯记忆曲线"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.word import Word, WordBook
from ..models.vocab import VocabProgress, VocabDailyLog
from ..schemas.vocab import (
    VocabWordOut, LearnRequest, ReviewRequest,
    VocabStatsOut, TodayTaskOut, VocabProgressOut,
)

router = APIRouter()

# 艾宾浩斯记忆曲线复习间隔（天）
EBBINGHAUS_INTERVALS = [1, 2, 4, 7, 15, 30]
# 每天新学单词数
NEW_WORDS_PER_DAY = 20


def _get_grade_books(db: Session, grade: int) -> List[int]:
    """获取指定年级的所有词库ID"""
    books = db.query(WordBook).filter(WordBook.grade == grade).all()
    return [b.id for b in books]


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


@router.get("/today", response_model=TodayTaskOut, summary="获取今日学习任务")
def get_today_words(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    db: Session = Depends(get_db),
):
    """获取今日学习任务：新词 + 待复习词"""
    today = date.today()
    book_ids = _get_grade_books(db, grade)

    if not book_ids:
        return TodayTaskOut(new_words=[], review_words=[], stats={
            "total_words": 0, "learned": 0, "mastered": 0, "due_today": 0
        })

    # 1. 获取待复习词（next_review_date <= today 且 status=learning）
    review_progress = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "learning",
        VocabProgress.next_review_date <= today,
        VocabProgress.word_id.in_(
            db.query(Word.id).filter(Word.book_id.in_(book_ids))
        )
    ).all()

    review_word_ids = [p.word_id for p in review_progress]
    review_words = []
    if review_word_ids:
        words_map = {w.id: w for w in db.query(Word).filter(Word.id.in_(review_word_ids)).all()}
        prog_map = {p.word_id: p for p in review_progress}
        for wid in review_word_ids:
            w = words_map.get(wid)
            p = prog_map.get(wid)
            if w and p:
                review_words.append(VocabWordOut(
                    word_id=w.id, word=w.word, phonetic=w.phonetic or "",
                    pos=w.pos or "", meaning=w.meaning, unit=w.unit or "",
                    difficulty=w.difficulty or 1, is_new=False,
                    review_stage=p.review_stage,
                ))

    # 2. 获取今日新词（排除已学过的）
    learned_word_ids = db.query(VocabProgress.word_id).filter(
        VocabProgress.user_id == user_id
    ).subquery()

    # 今天已经学过的词
    today_log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date == today
    ).first()
    already_new_today = today_log.new_words_learned if today_log else 0
    remaining_new = max(0, NEW_WORDS_PER_DAY - already_new_today)

    new_words = []
    if remaining_new > 0:
        # 按难度排序取未学过的词
        new_candidates = db.query(Word).filter(
            Word.book_id.in_(book_ids),
            ~Word.id.in_(db.query(learned_word_ids))
        ).order_by(Word.difficulty, Word.id).limit(remaining_new).all()

        for w in new_candidates:
            new_words.append(VocabWordOut(
                word_id=w.id, word=w.word, phonetic=w.phonetic or "",
                pos=w.pos or "", meaning=w.meaning, unit=w.unit or "",
                difficulty=w.difficulty or 1, is_new=True, review_stage=0,
            ))

    # 统计
    total_words = db.query(Word).filter(Word.book_id.in_(book_ids)).count()
    learned_count = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(book_ids)))
    ).count()
    mastered_count = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "mastered",
        VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(book_ids)))
    ).count()

    return TodayTaskOut(
        new_words=new_words,
        review_words=review_words,
        stats={
            "total_words": total_words,
            "learned": learned_count,
            "mastered": mastered_count,
            "due_today": len(review_words),
            "new_remaining": remaining_new,
        }
    )


@router.post("/learn", summary="标记新词已学会")
def mark_words_learned(
    req: LearnRequest,
    db: Session = Depends(get_db),
):
    """标记新词为已学习，设置首次复习日期"""
    today = date.today()
    results = []

    log = _get_today_log(db, req.user_id, today)

    for wid in req.word_ids:
        # 检查是否已有进度
        existing = db.query(VocabProgress).filter(
            VocabProgress.user_id == req.user_id,
            VocabProgress.word_id == wid,
        ).first()

        if existing:
            results.append({"word_id": wid, "status": "already_exists"})
            continue

        # 创建新进度记录
        progress = VocabProgress(
            user_id=req.user_id,
            word_id=wid,
            status="learning",
            review_stage=0,
            first_learn_date=today,
            last_review_date=today,
            next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),  # 1天后复习
            correct_count=1,
            total_reviews=1,
        )
        db.add(progress)
        log.new_words_learned += 1
        log.correct_count += 1
        results.append({"word_id": wid, "status": "learned", "next_review": str(progress.next_review_date)})

    db.commit()
    return {"updated": len(results), "details": results}


@router.post("/review", summary="提交复习结果")
def submit_review(
    req: ReviewRequest,
    db: Session = Depends(get_db),
):
    """提交复习结果，更新艾宾浩斯曲线进度"""
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []

    for item in req.results:
        wid = item.get("word_id")
        correct = item.get("correct", False)

        progress = db.query(VocabProgress).filter(
            VocabProgress.user_id == req.user_id,
            VocabProgress.word_id == wid,
        ).first()

        if not progress:
            results.append({"word_id": wid, "status": "not_found"})
            continue

        progress.total_reviews += 1
        progress.last_review_date = today
        log.words_reviewed += 1

        if correct:
            progress.correct_count += 1
            log.correct_count += 1
            # 答对：推进到下一阶段
            progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
            progress.next_review_date = _calc_next_review(progress.review_stage, today)

            # 达到最高阶段后标记为掌握
            if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
                progress.status = "mastered"

            results.append({
                "word_id": wid, "status": "correct",
                "next_stage": progress.review_stage,
                "next_review": str(progress.next_review_date),
            })
        else:
            progress.wrong_count += 1
            log.wrong_count += 1
            # 答错：回退到第一阶段重新开始
            progress.review_stage = 0
            progress.next_review_date = today + timedelta(days=EBBINGHAUS_INTERVALS[0])
            progress.status = "learning"

            results.append({
                "word_id": wid, "status": "wrong",
                "reset_to_stage": 0,
                "next_review": str(progress.next_review_date),
            })

    db.commit()
    return {"updated": len(results), "details": results}


# ═══════════════════════════════════════════════════════════
# 听写（默写）：全对才算通过，通过后才落库
# ═══════════════════════════════════════════════════════════

class DictateItem(BaseModel):
    word_id: int
    answer: str = ""


class DictateRequest(BaseModel):
    user_id: str
    mode: str = "new"  # new=新学 / review=复习
    results: List[DictateItem]


@router.post("/dictate", summary="单词听写判分：全对才落库（new=学会 / review=复习推进）")
def dictate_words(req: DictateRequest, db: Session = Depends(get_db)):
    """默写判分（规则：全对才算通过）：

    - 判分忽略大小写与首尾空白（如 Apple/apple 均正确）
    - mode=new：全部拼写正确 → 与「标记学会」相同落库（建进度 + 今日新学数 +N）；
      有拼写错误 → 不落库，返回错词及正确答案，孩子重默
    - mode=review：全部正确 → 按全部 correct 提交复习（记忆曲线推进）；
      有错误 → 不落库（孩子重默，错词也一并返回）
    """
    today = date.today()
    wrong = []
    for it in req.results:
        w = db.query(Word).filter(Word.id == it.word_id).first()
        key = (w.word or "").strip().lower() if w else ""
        ans = (it.answer or "").strip().lower()
        if not w or ans != key:
            wrong.append({"word_id": it.word_id, "correct": False,
                          "correct_answer": w.word if w else ""})
    if not req.results or wrong:
        return {"passed": False, "wrong": wrong, "updated": 0}

    log = _get_today_log(db, req.user_id, today)
    if req.mode == "new":
        # 全对 → 与 /learn 相同：建进度记录
        for it in req.results:
            existing = db.query(VocabProgress).filter(
                VocabProgress.user_id == req.user_id,
                VocabProgress.word_id == it.word_id,
            ).first()
            if existing:
                continue
            progress = VocabProgress(
                user_id=req.user_id, word_id=it.word_id,
                status="learning", review_stage=0,
                first_learn_date=today, last_review_date=today,
                next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),
                correct_count=1, total_reviews=1,
            )
            db.add(progress)
            log.new_words_learned += 1
            log.correct_count += 1
    else:
        # 全对 → 全部按 correct 提交复习
        for it in req.results:
            progress = db.query(VocabProgress).filter(
                VocabProgress.user_id == req.user_id,
                VocabProgress.word_id == it.word_id,
            ).first()
            if not progress:
                continue
            progress.total_reviews += 1
            progress.last_review_date = today
            progress.correct_count += 1
            progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
            progress.next_review_date = _calc_next_review(progress.review_stage, today)
            if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
                progress.status = "mastered"
            log.words_reviewed += 1
            log.correct_count += 1
    db.commit()
    return {"passed": True, "wrong": [], "updated": len(req.results)}


@router.get("/stats", response_model=VocabStatsOut, summary="用户词汇学习统计")
def get_vocab_stats(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    db: Session = Depends(get_db),
):
    """获取用户词汇学习统计"""
    today = date.today()
    book_ids = _get_grade_books(db, grade)

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
    """查看用户所有单词的学习进度"""
    book_ids = _get_grade_books(db, grade)
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
