"""背单词：今日任务 / 学习 / 复习 / 听写"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.word import Word, WordBook
from app.models.vocab import VocabProgress, VocabDailyLog
from app.routers.tasks import get_daily_quota, _load_study_flags

from . import router
from .common import (
    EBBINGHAUS_INTERVALS,
    NEW_WORDS_PER_DAY,
    _get_grade_books,
    _career_book_ids,
    _sync_unit_filter,
    _get_today_log,
    _calc_next_review,
    VocabWordOut,
    LearnRequest,
    ReviewRequest,
    TodayTaskOut,
)


@router.get("/today", response_model=TodayTaskOut, summary="获取今日学习任务")
def get_today_words(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    db: Session = Depends(get_db),
):
    """获取今日学习任务：新词 + 待复习词"""
    today = date.today()
    career_ids = _career_book_ids(db, grade, user_id)   # 累计统计：整个学生生涯
    stage_ids = _get_grade_books(db, grade, user_id)    # 新学选材：当前阶段

    if not career_ids:
        return TodayTaskOut(new_words=[], review_words=[], stats={
            "total_words": 0, "learned": 0, "mastered": 0, "due_today": 0
        })

    # 1. 获取待复习词（next_review_date <= today 且 status=learning）
    review_progress = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "learning",
        VocabProgress.next_review_date <= today,
        VocabProgress.word_id.in_(
            db.query(Word.id).filter(Word.book_id.in_(career_ids))
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

    # 2. 获取新词（排除已学过的）：不限制每日轮数，每轮按额度返回下一批未学词
    learned_word_ids = db.query(VocabProgress.word_id).filter(
        VocabProgress.user_id == user_id
    ).subquery()

    # 每轮新学额度由家长配置（默认 NEW_WORDS_PER_DAY）
    remaining_new = get_daily_quota(db, user_id, "daily_new_words")

    new_words = []
    if remaining_new > 0:
        # 按难度排序取未学过的词；sync_mode 开启时先按当前 unit 同步，额度不足回退全量
        # 新学选材来自当前阶段词库（stage_ids），不跨低年级
        base_q = db.query(Word).filter(
            Word.book_id.in_(stage_ids),
            ~Word.id.in_(db.query(learned_word_ids))
        )
        flags = _load_study_flags(db, user_id)
        sync = _sync_unit_filter(db, user_id, stage_ids)
        # xsc_bridge：六年级升初衔接，新学批次按 7:3 混入七年级词
        bridge_n = remaining_new * 3 // 10 if (grade == 6 and flags.get("xsc_bridge")) else 0
        main_n = remaining_new - bridge_n

        main_candidates = []
        if sync:
            sync_book_id, sync_unit = sync
            main_candidates = base_q.filter(
                Word.book_id == sync_book_id,
                Word.unit == sync_unit,
            ).order_by(Word.difficulty, Word.id).limit(main_n).all()
        if not sync or len(main_candidates) < main_n:
            main_candidates = base_q.order_by(Word.difficulty, Word.id).limit(main_n).all()

        new_candidates = list(main_candidates)
        if bridge_n:
            bridge_books = db.query(WordBook.id).filter(WordBook.grade == 7)
            new_candidates += db.query(Word).filter(
                Word.book_id.in_(bridge_books),
                ~Word.id.in_(db.query(learned_word_ids)),
            ).order_by(Word.difficulty, Word.id).limit(bridge_n).all()

        for w in new_candidates:
            new_words.append(VocabWordOut(
                word_id=w.id, word=w.word, phonetic=w.phonetic or "",
                pos=w.pos or "", meaning=w.meaning, unit=w.unit or "",
                difficulty=w.difficulty or 1, is_new=True, review_stage=0,
            ))

    # 统计（累计口径：整个学生生涯，career_ids）
    total_words = db.query(Word).filter(Word.book_id.in_(career_ids)).count()
    learned_count = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(career_ids)))
    ).count()
    mastered_count = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "mastered",
        VocabProgress.word_id.in_(db.query(Word.id).filter(Word.book_id.in_(career_ids)))
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


class DictateItem(BaseModel):
    word_id: int
    answer: str = ""


class DictateRequest(BaseModel):
    user_id: str
    mode: str = "new"  # new=新学 / review=复习
    results: List[DictateItem]


@router.post("/dictate", summary="单词听写判分：逐词存储（做对记录进度，做错进错题本）")
def dictate_words(req: DictateRequest, db: Session = Depends(get_db)):
    """默写判分（规则：逐词判分，做对即记录进度，做错不记录）：

    - 判分忽略大小写与首尾空白（如 Apple/apple 均正确）
    - mode=new：拼写正确 → 建/保留进度记录（今日新学数 +1）；错误词不记录，返回供前端进错题本
    - mode=review：拼写正确 → 推进该词记忆曲线；错误词不记录
    - 返回 saved(已记录的 word_id 列表)、wrong(错词及正确答案)、updated(记录数)、passed(是否全对)
      这样前端无需「整批从头重来」：做对的即时保存，做错的进入错题本后续巩固。
    """
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    saved: list = []
    wrong: list = []

    for it in req.results:
        w = db.query(Word).filter(Word.id == it.word_id).first()
        key = (w.word or "").strip().lower() if w else ""
        ans = (it.answer or "").strip().lower()
        if not w or ans != key:
            wrong.append({"word_id": it.word_id, "correct": False,
                          "correct_answer": w.word if w else ""})
            continue
        # 拼写正确 → 记录进度（按词独立落库）
        if req.mode == "new":
            existing = db.query(VocabProgress).filter(
                VocabProgress.user_id == req.user_id,
                VocabProgress.word_id == it.word_id,
            ).first()
            if not existing:
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
            progress = db.query(VocabProgress).filter(
                VocabProgress.user_id == req.user_id,
                VocabProgress.word_id == it.word_id,
            ).first()
            if not progress:
                # 复习但无进度记录：跳过记录（不计为错），避免误入错题本
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
        saved.append(it.word_id)

    db.commit()
    return {"passed": len(wrong) == 0, "saved": saved, "wrong": wrong,
            "updated": len(saved)}


__all__ = [
    "DictateItem",
    "DictateRequest",
    "get_today_words",
    "mark_words_learned",
    "submit_review",
    "dictate_words",
]
