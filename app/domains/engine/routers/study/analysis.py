"""自我超越、错因聚合分析相关端点"""
from datetime import date, datetime, timedelta
from collections import defaultdict
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
from app.models.kp_map import QuestionKpMap
from app.models.knowledge import KnowledgePoint


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


@router.get("/errors/by-kp", summary="错题知识点归因（弱项诊断）")
def errors_by_kp(
    user_id: str = Query(..., description="用户名"),
    subject: Optional[str] = Query(None, description="学科筛选（缺省全部）"),
    limit: int = Query(20, ge=1, le=50, description="返回知识点数量上限"),
    db: Session = Depends(get_db),
):
    """把「错题本」按知识点聚合，定位薄弱知识点（错题归因的「知识点」维度）。

    与掌握度模型（/api/mastery/heatmap 由真实作答推导）互补：
    本端点直接从「错题本」出发，回答「我哪些知识点错得最多」，驱动针对性复习。
    数据依赖 question_kp_map 标注；未标注的题目不计入 by_kp（仍计入 total_wrong）。
    """
    q = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
    ).join(Question)
    if subject:
        q = q.filter(Question.subject == subject)
    # 仅未掌握错题参与弱项归因（NULL 与 False 均纳入）
    wrong_recs = q.filter(WrongRecord.is_mastered != True).all()  # noqa: E712
    qids = [r.question_id for r in wrong_recs]
    if not qids:
        return {"total_wrong": 0, "mapped_wrong": 0, "by_kp": []}

    # 批量取题→知识点映射（仅 questions 题源、active）
    maps = db.query(QuestionKpMap).filter(
        QuestionKpMap.source_table == "questions",
        QuestionKpMap.question_id.in_(qids),
        QuestionKpMap.status == "active",
    ).all()
    kp_ids = {m.kp_id for m in maps}
    kps = {k.id: k for k in db.query(KnowledgePoint).filter(
        KnowledgePoint.id.in_(kp_ids)).all()} if kp_ids else {}

    # 统计：一题可能映射多个知识点，每个知识点各计一次
    agg = defaultdict(lambda: {"wrong": 0, "qids": set()})
    for m in maps:
        agg[m.kp_id]["wrong"] += 1
        agg[m.kp_id]["qids"].add(m.question_id)

    by_kp = []
    for kp_id, d in agg.items():
        kp = kps.get(kp_id)
        by_kp.append({
            "kp_id": kp_id,
            "kp_title": kp.title if kp else f"知识点#{kp_id}",
            "subject": kp.subject if kp else "",
            "unit": kp.unit if kp else "",
            "wrong_count": d["wrong"],
            "pending_count": len(d["qids"]),
            "question_ids": sorted(d["qids"]),
        })
    by_kp.sort(key=lambda x: (-x["wrong_count"], x["kp_title"]))

    return {
        "total_wrong": len(wrong_recs),
        "mapped_wrong": sum(len(d["qids"]) for d in agg.values()),
        "by_kp": by_kp[:limit],
    }


__all__ = ["self_compare", "analyze_errors", "errors_by_kp"]
