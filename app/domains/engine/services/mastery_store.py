"""掌握度 DB 编排（S3-M3 / 07 §5.1.1 + §4.3）

把「读作答 → 按 kp 分组 → compute_mastery → UPSERT mastery_records」的 DB 编排集中在此，
供：
- 用户端 POST /api/mastery/recompute（M3，单用户按需重算）；
- 答题后异步增量触发（M5）；
- 离线全量重算脚本 tools/recompute_mastery.py（M5）。

🔴 持连铁律：本模块仅做 DB 读写，**无任何外部阻塞调用**（无 AI / 无 HTTP / 无 SMTP）。
纯计算在 `mastery.py` 的 `compute_mastery`（无 IO）；本模块只负责「取数 + 落库」。
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domains.engine.services.mastery import (
    ALGO_VERSION,
    AnswerRecord,
    MasteryParams,
    compute_mastery,
)
from app.models.exam import AttemptAnswer, ExamAttempt  # AttemptAnswer 经 attempt_id → ExamAttempt.user_id 关联用户
from app.models.knowledge import KnowledgePoint
from app.models.kp_map import QuestionKpMap
from app.models.mastery import MasteryRecord

# 作答记录的题源固定为 questions 表（AttemptAnswer.question_id 外键指向 questions.id）
_QA_SOURCE = "questions"


def build_answer_records(
    db: Session, user_id: str, limit: int = 1000
) -> Dict[int, List[AnswerRecord]]:
    """拉取该用户最近 limit 条「有 kp 标注」的作答，按 kp_id 分组返回。

    BR-M0-1-04：只看有 kp 标注的作答（已通过 JOIN question_kp_map 保证）。
    """
    rows = (
        db.query(AttemptAnswer, QuestionKpMap.kp_id)
        .join(ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id)
        .join(
            QuestionKpMap,
            (QuestionKpMap.question_id == AttemptAnswer.question_id)
            & (QuestionKpMap.source_table == _QA_SOURCE),
        )
        .filter(ExamAttempt.user_id == user_id)
        .order_by(AttemptAnswer.created_at.desc())
        .limit(limit)
        .all()
    )
    grouped: Dict[int, List[AnswerRecord]] = {}
    for ans, kp_id in rows:
        answered_at = ans.started_at or ans.created_at or datetime.now()
        rec = AnswerRecord(
            answered_at=answered_at,
            is_correct=bool(ans.is_correct),
            duration_ms=int(ans.duration_ms or 0),
            difficulty=int(ans.difficulty or 3),
            kp_id=kp_id,
        )
        grouped.setdefault(kp_id, []).append(rec)
    return grouped


def recompute_user_mastery(
    db: Session, user_id: str, params: Optional[MasteryParams] = None
) -> int:
    """重算单个用户全部有标注知识点的掌握度并 UPSERT 到 mastery_records。

    返回本次重算的知识点数量。仅更新「当前有作答」的 kp（无新作答的 kp 保留上次结果）。
    无外部调用，持连安全。
    """
    p = params or MasteryParams()
    grouped = build_answer_records(db, user_id)

    # 知识点学科/年级冗余（便于按学科聚合）
    kp_ids = list(grouped.keys())
    kp_meta: Dict[int, Tuple[str, int]] = {}
    if kp_ids:  # MySQL 不支持 IN () 空列表，须判空
        for kp in db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(kp_ids)).all():
            kp_meta[kp.id] = (kp.subject or "", int(kp.grade or 0))

    existing = {
        mr.kp_id: mr
        for mr in db.query(MasteryRecord).filter_by(user_id=user_id).all()
    }

    now = datetime.now()
    for kp_id, recs in grouped.items():
        res = compute_mastery(recs, p)
        subj, grade = kp_meta.get(kp_id, ("", 0))
        mr = existing.get(kp_id)
        if mr is None:
            mr = MasteryRecord(user_id=user_id, kp_id=kp_id, created_at=now)
            db.add(mr)
        mr.subject = subj
        mr.grade = grade
        mr.mastery = res.mastery
        mr.level = res.level
        mr.answer_count = res.answer_count
        mr.correct_count = res.correct_count
        mr.correct_rate = res.correct_rate
        mr.avg_duration_ms = res.avg_duration_ms
        mr.last_answer_at = res.last_answer_at
        mr.correct_streak = res.correct_streak
        mr.confidence = res.confidence
        mr.algo_version = res.algo_version
        mr.computed_at = now
        mr.updated_at = now

    db.commit()
    return len(grouped)


def _level_bucket(level: str) -> str:
    return {"已掌握": "mastered", "基本掌握": "basic", "薄弱": "weak"}.get(level, "unknown")


def get_user_mastery_matrix(db: Session, user_id: str) -> dict:
    """后台：返回任意用户的掌握度矩阵（按学科分组 + 整体汇总）。

    纯 DB 读，无外部调用。供 /api/admin/mastery/users/{user_id} 使用。
    """
    recs = db.query(MasteryRecord).filter_by(user_id=user_id).all()
    subjects: dict = {}
    overall = {"total": 0, "mastered": 0, "basic": 0, "weak": 0,
               "unknown": 0, "mastery_sum": 0}
    for r in recs:
        row = {
            "kp_id": r.kp_id,
            "subject": r.subject,
            "grade": int(r.grade or 0),
            "mastery": int(r.mastery),
            "level": r.level,
            "answer_count": int(r.answer_count),
            "correct_count": int(r.correct_count),
            "correct_rate": float(r.correct_rate),
            "avg_duration_ms": int(r.avg_duration_ms),
            "correct_streak": int(r.correct_streak),
            "confidence": float(r.confidence),
            "algo_version": r.algo_version,
            "computed_at": str(r.computed_at),
        }
        subjects.setdefault(r.subject or "未分类", []).append(row)
        overall["total"] += 1
        overall["mastery_sum"] += int(r.mastery)
        overall[_level_bucket(r.level)] += 1
    overall["avg_mastery"] = round(
        overall["mastery_sum"] / overall["total"]) if overall["total"] else 0
    overall.pop("mastery_sum", None)
    return {"user_id": user_id, "subjects": subjects, "overall": overall}


def get_coverage_report(db: Session) -> dict:
    """后台：知识点标注覆盖率报表（07 §4.3 /api/admin/mastery/coverage）。

    指标：知识点总数 / 已标注（有 question_kp_map）数 / 覆盖率；按学科拆分；
    以及已计算掌握度的用户数、mastery_records 行数（反映掌握度落地进度）。
    纯 DB 读，无外部调用。
    """
    from sqlalchemy import func

    total_kp = db.query(func.count(KnowledgePoint.id)).scalar() or 0
    # 已标注 = 拥有至少一条 question_kp_map 的知识点（取交集，排除孤儿映射）
    annotated_kp = (
        db.query(func.count(func.distinct(KnowledgePoint.id)))
        .join(QuestionKpMap, QuestionKpMap.kp_id == KnowledgePoint.id)
        .scalar() or 0
    )

    by_subject: dict = {}
    for subj, cnt in db.query(
            KnowledgePoint.subject, func.count(KnowledgePoint.id)
    ).group_by(KnowledgePoint.subject).all():
        by_subject[subj or "未分类"] = {
            "total_kp": cnt, "annotated_kp": 0, "coverage": 0.0}

    for subj, cnt in (
        db.query(KnowledgePoint.subject, func.count(func.distinct(QuestionKpMap.kp_id)))
        .join(QuestionKpMap, QuestionKpMap.kp_id == KnowledgePoint.id)
        .group_by(KnowledgePoint.subject)
        .all()
    ):
        if subj in by_subject:
            by_subject[subj]["annotated_kp"] = cnt
            by_subject[subj]["coverage"] = (
                round(cnt / by_subject[subj]["total_kp"], 4)
                if by_subject[subj]["total_kp"] else 0.0)

    computed_users = db.query(func.count(func.distinct(MasteryRecord.user_id))).scalar() or 0
    mastery_rows = db.query(func.count(MasteryRecord.id)).scalar() or 0
    coverage = round(annotated_kp / total_kp, 4) if total_kp else 0.0

    return {
        "total_kp": total_kp,
        "annotated_kp": annotated_kp,
        "coverage": coverage,
        "computed_users": computed_users,
        "mastery_records": mastery_rows,
        "by_subject": by_subject,
    }


__all__ = [
    "build_answer_records", "recompute_user_mastery",
    "get_user_mastery_matrix", "get_coverage_report", "ALGO_VERSION",
]
