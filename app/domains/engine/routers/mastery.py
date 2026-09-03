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
from app.domains.engine.services.mastery import ALGO_VERSION
from app.domains.engine.services.mastery_store import recompute_user_mastery
from app.models.exam import AttemptAnswer, ExamAttempt
from app.models.knowledge import KnowledgePoint
from app.models.kp_map import QuestionKpMap
from app.models.mastery import MasteryRecord
from app.models.user import User

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
