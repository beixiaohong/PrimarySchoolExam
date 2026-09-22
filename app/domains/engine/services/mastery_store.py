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
from app.models.exam import AttemptAnswer, ExamAttempt, Question  # AttemptAnswer 经 attempt_id → ExamAttempt.user_id 关联用户
from app.models.knowledge import KnowledgePoint
from app.models.kp_map import QuestionKpMap
from app.models.mastery import MasteryRecord, MasterySnapshot, MasteryPractice

# 作答记录的题源固定为 questions 表（AttemptAnswer.question_id 外键指向 questions.id）
_QA_SOURCE = "questions"

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("engine.mastery_store")

# 增量重算线程池：答题接口 fire-and-forget 投递，避免阻塞 HTTP 响应（07 §5.1.1 步骤2）。
# 工作线程自开短会话、纯 DB 计算（无外部阻塞调用），持连铁律安全。
_recompute_executor = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="mastery-recompute")


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

    # 智能推题练习也计入掌握度（闭环）：每条 mastery_practice 直接归属其 kp_id，
    # 与真实考试作答同等对待（纯 DB 读，无外部调用）。
    for pr in db.query(MasteryPractice).filter(MasteryPractice.user_id == user_id).all():
        if not pr.kp_id:
            continue
        rec = AnswerRecord(
            answered_at=pr.answered_at or datetime.now(),
            is_correct=bool(pr.is_correct),
            duration_ms=int(pr.duration_ms or 0),
            difficulty=int(pr.difficulty or 3),
            kp_id=pr.kp_id,
        )
        grouped.setdefault(pr.kp_id, []).append(rec)
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


def record_mastery_practice(
    db: Session, user_id: str, items: List[Dict[str, object]]
) -> int:
    """记录智能推题练习结果并落库（MVP#1 闭环写入）。

    items: [{question_id, kp_id, is_correct, duration_ms, difficulty}, ...]
    纯 DB 写，无外部调用；调用方负责提交后触发增量重算（trigger_incremental_recompute）。
    返回写入条数。
    """
    now = datetime.now()
    n = 0
    for it in items:
        qid = int(it.get("question_id") or 0)
        if not qid:
            continue
        db.add(MasteryPractice(
            user_id=user_id,
            kp_id=int(it.get("kp_id") or 0),
            question_id=qid,
            is_correct=1 if it.get("is_correct") else 0,
            duration_ms=int(it.get("duration_ms") or 0),
            difficulty=int(it.get("difficulty") or 3),
            answered_at=now,
        ))
        n += 1
    db.commit()
    return n


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


def recommend_questions_by_mastery(
    db: Session, user_id: str,
    limit: int = 30, per_kp: int = 5,
    min_mastery: int = 0, max_mastery: int = 79,
) -> dict:
    """按知识点智能推题（MVP#1 核心）：依据用户掌握度，从薄弱/基本掌握的知识点
    抽取针对性练习题目。

    - 选点：`mastery_records` 中 mastery ∈ [min,max]（默认 <80：未掌握/薄弱/基本掌握），
      优先最薄弱（mastery 升序）；
    - 取题：经 `question_kp_map(source='questions')` 取该 kp 题目，主知识点优先；
    - 去重：排除用户已答对过的题（AttemptAnswer.is_correct），避免无效重复；
    - 限流：每 kp 最多 per_kp 题、总量 limit，确定性选取（主>副、难度升序、题号升序）。
    纯 DB 读，无外部调用，持连安全。
    """
    weak = (
        db.query(MasteryRecord)
        .filter(MasteryRecord.user_id == user_id,
                MasteryRecord.mastery >= min_mastery,
                MasteryRecord.mastery <= max_mastery)
        .order_by(MasteryRecord.mastery.asc(), MasteryRecord.kp_id.asc())
        .all()
    )
    if not weak:
        return {"user_id": user_id, "weak_kp_count": 0, "total": 0, "groups": []}

    weak_kp_ids = [w.kp_id for w in weak]

    # 知识点标题（一次 IN 查询）
    kp_titles: Dict[int, str] = {}
    if weak_kp_ids:
        for kp in db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(weak_kp_ids)).all():
            kp_titles[kp.id] = kp.title

    # 已答对题（排除，避免重复推已会题）
    answered_correct = {
        r[0] for r in (
            db.query(AttemptAnswer.question_id)
            .join(ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id)
            .filter(ExamAttempt.user_id == user_id,
                    AttemptAnswer.is_correct.is_(True))
            .all()
        )
    }

    # 取题：kp -> 候选题（主知识点优先）
    kp_questions: Dict[int, List[dict]] = {}
    if weak_kp_ids:
        maps = (
            db.query(QuestionKpMap.question_id, QuestionKpMap.kp_id,
                     QuestionKpMap.is_primary, QuestionKpMap.weight)
            .filter(QuestionKpMap.source_table == _QA_SOURCE,
                    QuestionKpMap.kp_id.in_(weak_kp_ids),
                    QuestionKpMap.status == "active")
            .all()
        )
        wanted = list(dict.fromkeys(m.question_id for m in maps
                                    if m.question_id not in answered_correct))
        qmap = {q.id: q for q in db.query(Question).filter(Question.id.in_(wanted)).all()
                } if wanted else {}
        for m in maps:
            q = qmap.get(m.question_id)
            if q is None:
                continue
            kp_questions.setdefault(m.kp_id, []).append({
                "question_id": q.id,
                "subject": q.subject,
                "type_code": q.type_code or "",
                "type_name": q.type_name or "",
                "difficulty": int(q.difficulty or 1),
                "question": q.question,
                "options_json": q.options_json or "",
                "answer": q.answer or "",
                "image_path": q.image_path or "",
                "is_primary": int(m.is_primary),
            })

    # 限流 + 组装（按最薄弱的知识点优先）
    groups = []
    total = 0
    for w in weak:
        items = kp_questions.get(w.kp_id)
        if not items:
            continue
        items.sort(key=lambda x: (-x["is_primary"], x["difficulty"], x["question_id"]))
        items = items[:per_kp]
        total += len(items)
        groups.append({
            "kp_id": w.kp_id,
            "kp_title": kp_titles.get(w.kp_id, ""),
            "mastery": int(w.mastery),
            "level": w.level,
            "questions": items,
        })
        if total >= limit:
            break

    return {"user_id": user_id, "weak_kp_count": len(weak), "total": total, "groups": groups}


def get_mastery_graph(
    db: Session, user_id: str, subject: Optional[str] = None, grade: Optional[int] = None
) -> dict:
    """知识点图谱（MVP#1）：返回 KP 层级树（parent_id）+ 每个 KP 的掌握度（若有）。

    供前端渲染「知识点图谱」并按掌握度着色。纯 DB 读，无外部调用。
    subject 必填（限定范围，避免一次性返回全量知识点）；grade 可选进一步收窄。
    """
    q = db.query(KnowledgePoint)
    if subject:
        q = q.filter(KnowledgePoint.subject == subject)
    if grade is not None:
        q = q.filter(KnowledgePoint.grade == grade)
    kps = q.all()

    mmap = {m.kp_id: m for m in db.query(MasteryRecord).filter_by(user_id=user_id).all()}
    nodes = []
    for kp in kps:
        m = mmap.get(kp.id)
        nodes.append({
            "kp_id": kp.id,
            "parent_id": int(kp.parent_id or 0),
            "subject": kp.subject,
            "grade": int(kp.grade or 0),
            "unit": kp.unit or "",
            "title": kp.title,
            "difficulty": int(kp.difficulty or 1),
            "mastery": int(m.mastery) if m else None,
            "level": m.level if m else None,
        })
    return {"user_id": user_id, "subject": subject, "grade": grade, "nodes": nodes}


def trigger_incremental_recompute(user_id: str) -> None:
    """增量触发：异步（线程池）重算某用户掌握度。

    设计（07 §5.1.1 + 持连铁律）：
    - 由答题接口在「写库提交、释放请求连接」之后 fire-and-forget 调用；
    - 工作线程自开短会话（不复用请求会话），纯 DB 计算，无外部阻塞调用；
    - 不阻塞 HTTP 响应；异常仅记录日志，不影响主流程。
    """
    def _job():
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            recompute_user_mastery(db, user_id)
        except Exception:
            logger.exception("增量掌握度重算失败 user=%s", user_id)
        finally:
            db.close()

    try:
        _recompute_executor.submit(_job)
    except Exception:
        logger.exception("投递增量掌握度重算失败 user=%s", user_id)


def generate_snapshots(db: Session, user_ids: Optional[List[str]] = None) -> int:
    """生成当日掌握度快照（07 §5.1.1 步骤5，每日 01:30）。

    对 mastery_records（可限定用户）按 uq_ms(user_id,kp_id,snap_date,algo_version) UPSERT；
    delta = 本次 mastery − 该 (user,kp,algo) 最近一次快照 mastery（无则 0）。
    纯 DB 写，无外部调用。返回生成的快照数。
    """
    from datetime import date

    from sqlalchemy import func

    today = date.today()
    q = db.query(MasteryRecord)
    if user_ids:
        q = q.filter(MasteryRecord.user_id.in_(user_ids))
    records = q.all()

    made = 0
    for r in records:
        prev = (
            db.query(MasterySnapshot.mastery)
            .filter(
                MasterySnapshot.user_id == r.user_id,
                MasterySnapshot.kp_id == r.kp_id,
                MasterySnapshot.algo_version == r.algo_version,
            )
            .order_by(MasterySnapshot.snap_date.desc())
            .first()
        )
        prev_mastery = int(prev[0]) if prev else 0
        delta = int(r.mastery) - prev_mastery

        snap = db.query(MasterySnapshot).filter_by(
            user_id=r.user_id, kp_id=r.kp_id,
            snap_date=today, algo_version=r.algo_version,
        ).first()
        if snap is None:
            snap = MasterySnapshot(
                user_id=r.user_id, kp_id=r.kp_id,
                snap_date=today, algo_version=r.algo_version,
            )
            db.add(snap)
        snap.mastery = int(r.mastery)
        snap.delta = delta
        made += 1
    db.commit()
    return made


__all__ = [
    "build_answer_records", "recompute_user_mastery", "record_mastery_practice",
    "recommend_questions_by_mastery", "get_mastery_graph",
    "get_user_mastery_matrix", "get_coverage_report",
    "trigger_incremental_recompute", "generate_snapshots", "ALGO_VERSION",
]
