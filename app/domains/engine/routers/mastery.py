"""掌握度用户端接口（S3-M3 / 07 §4.3）

前缀 /api/mastery，统一挂 user_auth_deps（严格账号绑定 require_self）：
- GET  /api/mastery/overview      用户掌握度总览（按学科聚合）
- GET  /api/mastery/heatmap       掌握度热力图（学科 × 知识点）
- GET  /api/mastery/kp/{kp_id}    单知识点掌握度 + 计算依据
- POST /api/mastery/recompute     触发本人掌握度重算（同步单用户；M5 提供异步/离线）

权限：本人（require_self）。他人重算属后台能力，由 M4 的 /api/admin/mastery/* 提供。
未标注完成时掌握度不可上线（BR-M0-1-04）：接口对空数据返回 0/未掌握，由前端按
computed_at / confidence 控制展示（DoD）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.contracts import require_self
from app.domains.assessment.contracts import _check_answer
from app.domains.engine.services.mastery import ALGO_VERSION
from app.domains.engine.services.mastery_store import (
    recompute_user_mastery,
    recommend_questions_by_mastery,
    get_mastery_graph,
    record_mastery_practice,
    trigger_incremental_recompute,
)
from app.models.exam import AttemptAnswer, ExamAttempt, Question
from app.models.knowledge import KnowledgePoint
from app.models.kp_map import QuestionKpMap
from app.models.mastery import MasteryRecord
from app.models.user import User
from pydantic import BaseModel
from typing import List

router = APIRouter()

_QA_SOURCE = "questions"


@router.get("/overview", summary="用户掌握度总览（按学科聚合）")
def mastery_overview(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """按学科聚合：每科总数 / 各档位数量 / 平均掌握度；并给出整体汇总。"""
    recs = db.query(MasteryRecord).filter_by(user_id=current_user.user_id).all()

    subjects: dict = {}
    overall = {"total": 0, "mastered": 0, "basic": 0, "weak": 0,
               "unknown": 0, "mastery_sum": 0}

    def _bucket(level: str) -> str:
        return {"已掌握": "mastered", "基本掌握": "basic",
                "薄弱": "weak"}.get(level, "unknown")

    for r in recs:
        key = r.subject or "未分类"
        s = subjects.setdefault(
            key, {"total": 0, "mastered": 0, "basic": 0,
                  "weak": 0, "unknown": 0, "mastery_sum": 0})
        s["total"] += 1
        s["mastery_sum"] += int(r.mastery)
        s[_bucket(r.level)] += 1

        overall["total"] += 1
        overall["mastery_sum"] += int(r.mastery)
        overall[_bucket(r.level)] += 1

    for s in subjects.values():
        s["avg_mastery"] = round(s["mastery_sum"] / s["total"]) if s["total"] else 0
        s.pop("mastery_sum", None)
    overall["avg_mastery"] = round(
        overall["mastery_sum"] / overall["total"]) if overall["total"] else 0
    overall.pop("mastery_sum", None)

    return {"subjects": subjects, "overall": overall}


@router.get("/heatmap", summary="掌握度热力图（学科 × 知识点）")
def mastery_heatmap(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """返回 学科 → [{kp_id, title, mastery, level}]，供前端热力图渲染。"""
    rows = (
        db.query(MasteryRecord, KnowledgePoint.title)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == MasteryRecord.kp_id)
        .filter(MasteryRecord.user_id == current_user.user_id)
        .all()
    )
    by_subject: dict = {}
    for r, title in rows:
        by_subject.setdefault(r.subject or "未分类", []).append({
            "kp_id": r.kp_id,
            "title": title or "",
            "mastery": int(r.mastery),
            "level": r.level,
        })
    return {"subjects": by_subject}


@router.get("/kp/{kp_id}", summary="单知识点掌握度 + 计算依据")
def mastery_kp(
    kp_id: int,
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """单知识点掌握度详情 + 最近若干作答（计算依据）。无数据返回 exists=False。"""
    r = db.query(MasteryRecord).filter_by(
        user_id=current_user.user_id, kp_id=kp_id).first()
    title = db.query(KnowledgePoint.title).filter_by(id=kp_id).scalar()

    if r is None:
        return {"kp_id": kp_id, "title": title or "", "exists": False,
                "mastery": None, "level": None}

    recent = (
        db.query(AttemptAnswer)
        .join(ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id)
        .join(
            QuestionKpMap,
            (QuestionKpMap.question_id == AttemptAnswer.question_id)
            & (QuestionKpMap.source_table == _QA_SOURCE),
        )
        .filter(ExamAttempt.user_id == current_user.user_id,
                QuestionKpMap.kp_id == kp_id)
        .order_by(AttemptAnswer.created_at.desc())
        .limit(20)
        .all()
    )
    basis = [{
        "answered_at": str(ans.started_at or ans.created_at),
        "is_correct": bool(ans.is_correct),
        "duration_ms": int(ans.duration_ms or 0),
    } for ans in recent]

    return {
        "kp_id": r.kp_id,
        "title": title or "",
        "exists": True,
        "mastery": int(r.mastery),
        "level": r.level,
        "subject": r.subject,
        "grade": int(r.grade or 0),
        "answer_count": int(r.answer_count),
        "correct_count": int(r.correct_count),
        "correct_rate": float(r.correct_rate),
        "avg_duration_ms": int(r.avg_duration_ms),
        "last_answer_at": str(r.last_answer_at) if r.last_answer_at else None,
        "correct_streak": int(r.correct_streak),
        "confidence": float(r.confidence),
        "algo_version": r.algo_version,
        "computed_at": str(r.computed_at),
        "basis": basis,
    }


@router.post("/recompute", summary="触发本人掌握度重算")
def mastery_recompute(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
    user_id: str = Query(None, description="目标用户；缺省=本人。他人重算请走后台接口"),
):
    """重算本人（或指定本人）的掌握度。他人重算需后台权限，此处拒绝（交由 M4）。"""
    target = user_id or current_user.user_id
    if target != current_user.user_id:
        raise HTTPException(
            403, "仅可触发本人掌握度重算；他人重算请走后台 /api/admin/mastery/* 接口")
    n = recompute_user_mastery(db, target)
    return {"user_id": target, "recomputed_kps": n, "algo_version": ALGO_VERSION}


# ═════════════════════════════════════════════════════════
# 智能推题 / 知识点图谱（MVP#1 · 掌握度模型 + 知识点图谱）
# ═════════════════════════════════════════════════════════

class MasteryPracticeItem(BaseModel):
    question_id: int
    kp_id: int = 0
    user_answer: str = ""
    is_correct: bool = False  # 仅前端初判；exam 题由后端 _check_answer 重判


class MasteryPracticeReq(BaseModel):
    user_id: str = ""
    items: List[MasteryPracticeItem]


@router.get("/recommend", summary="按知识点智能推题（薄弱/基本掌握针对性练习）")
def mastery_recommend(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
    limit: int = Query(30, ge=1, le=100, description="返回题目总量上限"),
    per_kp: int = Query(5, ge=1, le=20, description="单个知识点最多题目数"),
):
    """依据本人掌握度，从薄弱/基本掌握知识点抽取针对性练习题（闭环：练后提交 /practice 更新掌握度）。"""
    return recommend_questions_by_mastery(db, current_user.user_id, limit=limit, per_kp=per_kp)


@router.get("/graph", summary="知识点图谱（层级 + 掌握度着色）")
def mastery_graph(
    subject: str = Query(..., description="学科，如 数学/语文/英语"),
    grade: int = Query(..., description="年级 7-9"),
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """返回该学科+年级下知识点层级树，并附本人掌握度（用于图谱着色）。"""
    return get_mastery_graph(db, current_user.user_id, subject=subject, grade=grade)


@router.post("/practice", summary="提交智能推题练习（闭环：写库并触发掌握度重算）")
def mastery_practice(
    req: MasteryPracticeReq,
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """提交智能推题作答：后端对 exam 题重判（防作弊），写入 mastery_practice 并触发增量重算。"""
    target = req.user_id or current_user.user_id
    if target != current_user.user_id:
        raise HTTPException(403, "仅可提交本人练习结果")
    qids = [it.question_id for it in req.items if it.question_id]
    if qids:
        qmap = {q.id: q for q in db.query(Question).filter(Question.id.in_(qids)).all()}
        for it in req.items:
            q = qmap.get(it.question_id)
            if q:
                it.is_correct = bool(_check_answer(
                    it.user_answer or "", (q.answer or "").strip(), q.options_json))
    n = record_mastery_practice(db, target, [
        {"question_id": it.question_id, "kp_id": it.kp_id,
         "is_correct": bool(it.is_correct), "duration_ms": 0, "difficulty": 3}
        for it in req.items
    ])
    trigger_incremental_recompute(target)
    return {"accepted": n, "user_id": target, "recomputed": True}
