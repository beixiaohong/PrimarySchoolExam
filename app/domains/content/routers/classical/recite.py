"""古诗文：背诵会话（今日任务 / 学习 / 复习 / 默写）"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.classical import ClassicalText, ClassicalProgress, ClassicalDailyLog
from app.domains.engagement.contracts import get_daily_quota, _load_study_flags
from app.services import semester as _semester

from . import router
from .common import (
    DictateRequest,
    LearnRequest,
    ReviewRequest,
    EBBINGHAUS_INTERVALS,
    _pinyin_lines,
    _get_today_log,
    _get_streak,
    _calc_next_review,
)


@router.get("/today", summary="获取今日背诵任务")
def get_today_task(
    user_id: str = Query(...),
    grade: int = Query(6),
    db: Session = Depends(get_db),
):
    """获取今日任务：新学篇目 + 待复习篇目"""
    today = date.today()

    # 待复习
    review_progress = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "learning",
        ClassicalProgress.next_review_date <= today,
    ).all()

    review_items = []
    for p in review_progress:
        text = db.query(ClassicalText).filter(ClassicalText.id == p.text_id).first()
        if text:
            review_items.append({
                "text_id": text.id,
                "title": text.title,
                "author": text.author,
                "content": text.content,
                "pinyin": _pinyin_lines(text.content),
                "review_stage": p.review_stage,
                "next_review_date": str(p.next_review_date) if p.next_review_date else None,
            })

    # 新学：不限制每日轮数，每轮按额度返回下一批未背篇目
    # 每轮新背额度由家长配置（默认 NEW_TEXTS_PER_DAY）
    remaining = get_daily_quota(db, user_id, "daily_new_texts")

    new_items = []
    if remaining > 0:
        # 学期解锁：只开「全」+ 当前学期篇目，include_next 预支下学期
        semesters = ["全", _semester.current_semester()]
        if _load_study_flags(db, user_id).get("include_next"):
            semesters.append(_semester.next_semester())

        learned_ids = db.query(ClassicalProgress.text_id).filter(
            ClassicalProgress.user_id == user_id
        ).subquery()
        # xsc_bridge：六年级升初衔接，新背批次按 7:3 混入七年级篇目
        flags = _load_study_flags(db, user_id)
        bridge_n = remaining * 3 // 10 if (grade == 6 and flags.get("xsc_bridge")) else 0
        main_n = remaining - bridge_n
        candidates = db.query(ClassicalText).filter(
            ClassicalText.grade <= grade,
            or_(ClassicalText.semester.is_(None), ClassicalText.semester.in_(semesters)),
            ~ClassicalText.id.in_(db.query(learned_ids)),
        ).order_by(ClassicalText.grade, ClassicalText.title).limit(main_n).all()
        if bridge_n:
            candidates += db.query(ClassicalText).filter(
                ClassicalText.grade == 7,
                or_(ClassicalText.semester.is_(None), ClassicalText.semester.in_(semesters)),
                ~ClassicalText.id.in_(db.query(learned_ids)),
                ClassicalText.id.notin_([t.id for t in candidates]),
            ).order_by(ClassicalText.grade, ClassicalText.title).limit(bridge_n).all()

        for t in candidates:
            new_items.append({
                "text_id": t.id,
                "title": t.title,
                "author": t.author,
                "content": t.content,
                "text_type": t.text_type,
                "pinyin": _pinyin_lines(t.content),
            })

    # 统计
    total = db.query(ClassicalText).filter(ClassicalText.grade <= grade).count()
    learned = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.text_id.in_(
            db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        )
    ).count()
    mastered = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "mastered",
        ClassicalProgress.text_id.in_(
            db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        )
    ).count()

    return {
        "new_texts": new_items,
        "review_texts": review_items,
        "stats": {
            "total": total,
            "learned": learned,
            "mastered": mastered,
            "due_today": len(review_items),
            "new_remaining": remaining,
            "streak_days": _get_streak(db, user_id),
        }
    }


@router.post("/learn", summary="标记篇目已学习")
def mark_texts_learned(req: LearnRequest, db: Session = Depends(get_db)):
    """标记新学的篇目，设置首次复习日期"""
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []

    for tid in req.text_ids:
        existing = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == req.user_id,
            ClassicalProgress.text_id == tid,
        ).first()
        if existing:
            results.append({"text_id": tid, "status": "already_exists"})
            continue

        progress = ClassicalProgress(
            user_id=req.user_id,
            text_id=tid,
            status="learning",
            review_stage=0,
            first_learn_date=today,
            last_review_date=today,
            next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),
            correct_count=1,
            total_reviews=1,
        )
        db.add(progress)
        log.texts_learned += 1
        log.correct_count += 1
        results.append({"text_id": tid, "status": "learned"})

    db.commit()
    return {"updated": len(results), "details": results}


@router.post("/review", summary="提交背诵复习结果")
def submit_review(req: ReviewRequest, db: Session = Depends(get_db)):
    """提交复习结果，更新艾宾浩斯进度。

    wrong_items 非空时触发 AI 复审：AI 判对的篇目自动从 wrong 翻转为 correct。
    """
    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []
    ai_flipped: list = []

    # AI 复审：对前端判错的篇目做二次确认
    ai_approved_tids: set = set()
    if req.wrong_items:
        from app.domains.assessment.contracts import judge_wrong_items
        judge_items = []
        for wi in req.wrong_items:
            judge_items.append({
                "key": wi.get("text_id"),
                "question_id": None,
                "question": wi.get("question", ""),
                "answer": wi.get("answer", ""),
                "user_answer": wi.get("user_answer", ""),
                "subject": wi.get("subject", "语文"),
            })
        if judge_items:
            approved = judge_wrong_items(req.user_id, judge_items)
            for wi in req.wrong_items:
                tid = wi.get("text_id")
                verdict = approved.get(tid)
                if verdict and verdict.get("correct"):
                    ai_approved_tids.add(tid)
                    ai_flipped.append({
                        "text_id": tid,
                        "reason": verdict.get("reason", "AI 复审：答案正确"),
                    })

    for item in req.results:
        tid = item.get("text_id")
        correct = item.get("correct", False)
        # AI 复审翻转：前端判错但 AI 判对
        if not correct and tid in ai_approved_tids:
            correct = True

        progress = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == req.user_id,
            ClassicalProgress.text_id == tid,
        ).first()
        if not progress:
            results.append({"text_id": tid, "status": "not_found"})
            continue

        progress.total_reviews += 1
        progress.last_review_date = today
        log.texts_reviewed += 1

        if correct:
            progress.correct_count += 1
            log.correct_count += 1
            progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
            progress.next_review_date = _calc_next_review(progress.review_stage, today)
            if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
                progress.status = "mastered"
            results.append({"text_id": tid, "status": "correct", "next_review": str(progress.next_review_date)})
        else:
            progress.wrong_count += 1
            log.wrong_count += 1
            progress.review_stage = 0
            progress.next_review_date = today + timedelta(days=EBBINGHAUS_INTERVALS[0])
            progress.status = "learning"
            results.append({"text_id": tid, "status": "wrong", "next_review": str(progress.next_review_date)})

    db.commit()
    return {"updated": len(results), "details": results, "ai_flipped": ai_flipped}


@router.post("/dictate", summary="古诗文默写提交：分项存储（passed_ids 记录，错的剔除）")
def dictate_texts(req: DictateRequest, db: Session = Depends(get_db)):
    """默写结果提交（前端随机填空题判分，分项存储）：

    - 仅对 passed_ids（默写正确的篇目）记录进度；错的已剔除交前端进错题本
    - 向后兼容：未传 passed_ids 时回退使用 text_ids（旧前端整轮全对才调用）
    - text_ids / passed_ids 均为空 → 不落库，视为未通过
    - wrong_items 非空时触发 AI 复审：AI 判对的篇目自动翻转为 correct 并记入进度
    返回 saved(已记录篇目 id)、updated(记录数)、passed(是否通过)、ai_flipped(AI 翻转的篇目)。
    """
    record_ids = req.passed_ids if req.passed_ids else req.text_ids
    ai_flipped: list = []  # AI 复审翻转的篇目

    # AI 复审：对前端判错的篇目做二次确认（古诗文主要处理繁体/通假字/语序差异）
    if req.wrong_items:
        from app.domains.assessment.contracts import judge_wrong_items
        judge_items = []
        for wi in req.wrong_items:
            judge_items.append({
                "key": wi.get("text_id"),
                "question_id": None,
                "question": wi.get("question", ""),
                "answer": wi.get("answer", ""),
                "user_answer": wi.get("user_answer", ""),
                "subject": wi.get("subject", "语文"),
            })
        if judge_items:
            approved = judge_wrong_items(req.user_id, judge_items)
            for wi in req.wrong_items:
                tid = wi.get("text_id")
                verdict = approved.get(tid)
                if verdict and verdict.get("correct"):
                    ai_flipped.append({
                        "text_id": tid,
                        "reason": verdict.get("reason", "AI 复审：答案正确"),
                    })
                    if tid not in record_ids:
                        record_ids = list(record_ids) + [tid]

    if not record_ids:
        return {"passed": False, "saved": [], "updated": 0, "ai_flipped": ai_flipped}

    today = date.today()
    log = _get_today_log(db, req.user_id, today)
    results = []
    saved: list = []

    if req.mode == "new":
        for tid in record_ids:
            existing = db.query(ClassicalProgress).filter(
                ClassicalProgress.user_id == req.user_id,
                ClassicalProgress.text_id == tid,
            ).first()
            if existing:
                results.append({"text_id": tid, "status": "already_exists"})
                # 已存在仍计入 saved（避免前端重复处理），但不重复计数
                saved.append(tid)
                continue
            progress = ClassicalProgress(
                user_id=req.user_id, text_id=tid,
                status="learning", review_stage=0,
                first_learn_date=today, last_review_date=today,
                next_review_date=today + timedelta(days=EBBINGHAUS_INTERVALS[0]),
                correct_count=1, total_reviews=1,
            )
            db.add(progress)
            log.texts_learned += 1
            log.correct_count += 1
            results.append({"text_id": tid, "status": "learned"})
            saved.append(tid)
        db.commit()
        return {"passed": True, "saved": saved, "updated": len(saved), "details": results,
                "ai_flipped": ai_flipped}

    # mode=review：对 passed_ids 全部按 correct 提交复习
    for tid in record_ids:
        progress = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == req.user_id,
            ClassicalProgress.text_id == tid,
        ).first()
        if not progress:
            results.append({"text_id": tid, "status": "not_found"})
            continue
        progress.total_reviews += 1
        progress.last_review_date = today
        log.texts_reviewed += 1
        progress.correct_count += 1
        log.correct_count += 1
        progress.review_stage = min(progress.review_stage + 1, len(EBBINGHAUS_INTERVALS))
        progress.next_review_date = _calc_next_review(progress.review_stage, today)
        if progress.review_stage >= len(EBBINGHAUS_INTERVALS):
            progress.status = "mastered"
        results.append({"text_id": tid, "status": "correct",
                        "next_review": str(progress.next_review_date)})
        saved.append(tid)
    db.commit()
    return {"passed": True, "saved": saved, "updated": len(saved), "details": results,
            "ai_flipped": ai_flipped}


__all__ = [
    "get_today_task",
    "mark_texts_learned",
    "submit_review",
    "dictate_texts",
]
