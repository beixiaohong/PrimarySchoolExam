"""自我超越、错因聚合分析相关端点"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import router
from .common import CAUSE_LABELS
from app.database import get_db
from app.models.study_error import StudyError
from app.models.exam import WrongRecord, Question, ExamAttempt
from app.models.vocab import VocabDailyLog
from app.models.classical import ClassicalDailyLog


@router.get("/self-compare", summary="自我超越：最近两次做题/今昨背诵/本周错题对比")
def self_compare(
    user_id: str = Query(..., description="用户名"),
    subject: Optional[str] = Query(None, description="学科筛选（缺省全部）"),
    db: Session = Depends(get_db),
):
    """自我超越：与孩子自己比——最近两次做题得分差、今昨背诵量、本周新消灭错题数。

    参数（Query）：user_id、subject（可选）。
    返回：{attempts(对比), vocab(今/昨/差), classical, mastered_7d}。
    副作用：无（只读）。无需家长密码。
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    # 1) 做题对比：最近两次（按提交时间）
    from app.models.exam import ExamRecord
    q = db.query(ExamAttempt, ExamRecord.title).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id)
    q = q.filter(ExamAttempt.user_id == user_id)
    if subject:
        q = q.filter(ExamRecord.subject == subject)
    rows = q.order_by(ExamAttempt.id.desc()).limit(2).all()
    attempts_cmp = None
    if len(rows) >= 2:
        (last, last_title), (prev, prev_title) = rows[0], rows[1]
        attempts_cmp = {
            "last_correct": last.correct, "prev_correct": prev.correct,
            "delta_correct": last.correct - prev.correct,
            "last_score": last.score, "prev_score": prev.score,
            "delta_score": last.score - prev.score,
            "last_title": last_title or "最近一次",
        }
    elif len(rows) == 1:
        attempts_cmp = {"last_correct": rows[0][0].correct, "prev_correct": None,
                        "delta_correct": None, "last_score": rows[0][0].score,
                        "prev_score": None, "delta_score": None,
                        "last_title": rows[0][1] or "最近一次"}

    # 2) 单词：今天 vs 昨天新学
    def day_new_words(d):
        rows = db.query(VocabDailyLog).filter(
            VocabDailyLog.user_id == user_id,
            VocabDailyLog.learn_date == d,
        ).all()
        return sum(r.new_words_learned or 0 for r in rows)

    new_words_today, new_words_yday = day_new_words(today), day_new_words(yesterday)

    # 3) 古诗文：今天 vs 昨天学习量
    def day_classical(d):
        rows = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id,
            ClassicalDailyLog.learn_date == d,
        ).all()
        return sum((r.texts_learned or 0) + (r.texts_reviewed or 0) for r in rows)

    cls_today, cls_yday = day_classical(today), day_classical(yesterday)

    # 4) 本周消灭错题（7 天内新掌握）
    week_ago = datetime.combine(today - timedelta(days=7), datetime.min.time())
    mastered_7d = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
        WrongRecord.is_mastered == True,  # noqa: E712
        WrongRecord.mastered_at >= week_ago,
    ).count()

    return {
        "attempts": attempts_cmp,
        "vocab": {"today": new_words_today, "yesterday": new_words_yday,
                  "delta": new_words_today - new_words_yday},
        "classical": {"today": cls_today, "yesterday": cls_yday,
                      "delta": cls_today - cls_yday},
        "mastered_7d": mastered_7d,
    }


@router.get("/errors/analysis", summary="错因聚合分析")
def analyze_errors(
    user_id: str = Query(..., description="用户名"),
    subject: Optional[str] = Query(None, description="学科筛选（缺省为全部学科）"),
    db: Session = Depends(get_db),
):
    """错因四选分布 + 来源分布 + 学科分布 + 掌握情况（双轨合并统计）"""
    sq = db.query(StudyError).filter(StudyError.user_id == user_id)
    wrq = db.query(WrongRecord).filter(WrongRecord.user_id == user_id).join(Question)
    if subject:
        if subject == "英语":
            sq = sq.filter(StudyError.source_type.in_(["grammar", "vocab"]))
        elif subject == "语文":
            sq = sq.filter(StudyError.source_type == "classical")
        else:  # 数学学科无学习错题
            sq = sq.filter(StudyError.id == -1)
        wrq = wrq.filter(Question.subject == subject)
    study_errors = sq.all()
    wrong_records = wrq.all()

    by_cause = {c: {"count": 0, "mastered": 0, "pending": 0, "label": label}
                for c, label in CAUSE_LABELS.items()}
    by_source = {}
    by_subject = {}
    pending_unlabeled = 0  # 未标注错因的待巩固错题

    def _count(cause: str, mastered: bool, source: str, subject: str):
        nonlocal pending_unlabeled
        if cause in by_cause:
            by_cause[cause]["count"] += 1
            if mastered:
                by_cause[cause]["mastered"] += 1
            else:
                by_cause[cause]["pending"] += 1
        elif not mastered:
            pending_unlabeled += 1
        by_source[source] = by_source.get(source, 0) + 1
        if subject:
            by_subject[subject] = by_subject.get(subject, 0) + 1

    for e in study_errors:
        _count(e.cause or "", e.is_mastered, e.source_type,
               "英语" if e.source_type == "grammar" else "语文")
    for wr in wrong_records:
        _count(wr.cause or "", wr.is_mastered, "exam", wr.question.subject)

    cause_list = [
        {"code": c, "label": d["label"], "count": d["count"],
         "mastered": d["mastered"], "pending": d["pending"]}
        for c, d in by_cause.items()
    ]
    cause_list.sort(key=lambda x: -x["count"])

    source_list = [{"code": k, "count": v} for k, v in by_source.items()]
    subject_list = [{"name": k, "count": v} for k, v in by_subject.items()]
    subject_list.sort(key=lambda x: -x["count"])

    total = len(study_errors) + len(wrong_records)
    mastered_total = sum(1 for e in study_errors if e.is_mastered) + \
        sum(1 for w in wrong_records if w.is_mastered)

    return {
        "total": total,
        "pending": total - mastered_total,
        "mastered": mastered_total,
        "mastery_rate": round(mastered_total / total * 100, 1) if total else 0,
        "pending_unlabeled": pending_unlabeled,
        "by_cause": cause_list,
        "by_source": source_list,
        "by_subject": subject_list,
    }


__all__ = ["self_compare", "analyze_errors"]
