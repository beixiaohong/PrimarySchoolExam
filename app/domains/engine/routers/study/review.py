"""复习队列、明日复习队列相关端点"""
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from . import router
from app.database import get_db
from app.models.study_error import StudyError
from app.models.exam import WrongRecord, Question
from app.models.vocab import VocabProgress, VocabDailyLog
from app.models.classical import ClassicalProgress, ClassicalDailyLog
from app.models.word import Word, WordBook
from app.models.classical import ClassicalText


@router.get("/review-queue", summary="复习队列（遗忘曲线到期项）")
def review_queue(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """汇总今日到期的单词 / 古诗文复习项，按到期时间升序

    items: [{type: vocab/classical, id, title, subtitle, due_date, stage, overdue_days}]
    """
    today = date.today()
    items = []

    # ── 单词到期 ──
    book_ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
    if book_ids:
        word_ids_subq = db.query(Word.id).filter(Word.book_id.in_(book_ids))
        due = db.query(VocabProgress).filter(
            VocabProgress.user_id == user_id,
            VocabProgress.status == "learning",
            VocabProgress.next_review_date <= today,
            VocabProgress.word_id.in_(word_ids_subq),
        ).order_by(VocabProgress.next_review_date.asc()).limit(limit).all()
        if due:
            words = {w.id: w for w in db.query(Word).filter(
                Word.id.in_([p.word_id for p in due])).all()}
            for p in due:
                w = words.get(p.word_id)
                if not w:
                    continue
                items.append({
                    "type": "vocab",
                    "id": p.id,
                    "title": w.word,
                    "subtitle": w.meaning,
                    "due_date": str(p.next_review_date) if p.next_review_date else "",
                    "stage": p.review_stage,
                    "overdue_days": (today - p.next_review_date).days if p.next_review_date else 0,
                })

    # ── 古诗文到期 ──
    text_ids_subq = db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
    due_c = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "learning",
        ClassicalProgress.next_review_date <= today,
        ClassicalProgress.text_id.in_(text_ids_subq),
    ).order_by(ClassicalProgress.next_review_date.asc()).limit(limit).all()
    if due_c:
        texts = {t.id: t for t in db.query(ClassicalText).filter(
            ClassicalText.id.in_([p.text_id for p in due_c])).all()}
        for p in due_c:
            t = texts.get(p.text_id)
            if not t:
                continue
            items.append({
                "type": "classical",
                "id": p.id,
                "title": f"《{t.title}》",
                "subtitle": f"{t.author} · {t.dynasty}",
                "due_date": str(p.next_review_date) if p.next_review_date else "",
                "stage": p.review_stage,
                "overdue_days": (today - p.next_review_date).days if p.next_review_date else 0,
            })

    items.sort(key=lambda x: (x["overdue_days"] > 0, x["due_date"]))

    # ── 未来 3 天到期数（供首页时间轴） ──
    upcoming = {"t1": 0, "t2": 0, "t3": 0}
    tomorrow = today + timedelta(days=1)
    for offset, key in ((1, "t1"), (2, "t2"), (3, "t3")):
        d = tomorrow + timedelta(days=offset - 1)
        upcoming[key] = (
            db.query(VocabProgress).filter(
                VocabProgress.user_id == user_id,
                VocabProgress.status == "learning",
                VocabProgress.next_review_date == d,
            ).count()
            + db.query(ClassicalProgress).filter(
                ClassicalProgress.user_id == user_id,
                ClassicalProgress.status == "learning",
                ClassicalProgress.next_review_date == d,
            ).count()
        )

    return {"date": str(today), "count": len(items), "items": items[:limit], "upcoming": upcoming}


@router.get("/tomorrow-queue", summary="明日复习队列（重做仍错，建议明天再战的错题）")
def tomorrow_queue(
    user_id: str = Query(..., description="用户名"),
    subject: str = Query(None, description="学科筛选（数学/语文/英语，学习错题无学科概念时忽略）"),
    db: Session = Depends(get_db),
):
    """重做仍错的错题进入明日复习队列（next_review_date 非空且未掌握）。

    items: [{kind: exam/study, record_id, question, subject, module_name, cause, next_review_date}]
    """
    today = date.today()
    items = []

    # ── 试卷错题（wrong_records）──
    recs = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
        WrongRecord.next_review_date.isnot(None),
        WrongRecord.is_mastered.is_(False),
    ).all()
    if recs:
        qids = list({r.question_id for r in recs})
        qmap = {q.id: q for q in db.query(Question).filter(Question.id.in_(qids)).all()} if qids else {}
        for r in recs:
            q = qmap.get(r.question_id)
            if not q:
                continue
            if subject and q.subject != subject:
                continue
            items.append({
                "kind": "exam", "record_id": r.id,
                "question": q.question, "subject": q.subject,
                "module_name": q.type_name or "", "cause": r.cause or "",
                "next_review_date": str(r.next_review_date) if r.next_review_date else "",
            })

    # ── 学习错题（study_errors）──
    for r in db.query(StudyError).filter(
        StudyError.user_id == user_id,
        StudyError.next_review_date.isnot(None),
        StudyError.is_mastered.is_(False),
    ).all():
        items.append({
            "kind": "study", "record_id": r.id,
            "question": r.question, "subject": "语文" if r.source_type == "classical" else "英语",
            "module_name": r.module_name or "", "cause": r.cause or "",
            "next_review_date": str(r.next_review_date) if r.next_review_date else "",
        })

    items.sort(key=lambda x: x["next_review_date"])
    return {"date": str(today), "count": len(items), "items": items}


__all__ = ["review_queue", "tomorrow_queue"]
