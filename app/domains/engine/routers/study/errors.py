"""学习错题记录（双轨：StudyError）相关端点与请求模型"""
from datetime import date
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import router
from app.database import get_db
from app.models.study_error import StudyError


class StudyErrorItem(BaseModel):
    """学习错题单条记录（批量上报用）：来源类型、题源 ID、题目与正误答案、错因自评等。"""
    source_type: str  # grammar / classical
    source_id: int = 0
    module_name: str = ""
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    explanation: str = ""
    cause: str = ""  # 错因自评（可选）


class StudyErrorRecordRequest(BaseModel):
    """学习错题批量上报请求体：含用户标识与一组错题条目。"""
    user_id: str
    items: List[StudyErrorItem]


class StudyErrorMasterRequest(BaseModel):
    """标记学习错题已掌握请求体：含用户标识与目标错题 ID。"""
    user_id: str
    error_id: int


@router.post("/errors", summary="记录学习错题（批量，自动去重累计）")
def record_study_errors(req: StudyErrorRecordRequest, db: Session = Depends(get_db)):
    """记录学习模块错题。

    同一用户 + 来源 + 题目标识只保留一条记录，重复答错累计 error_count。
    """
    if not req.items:
        return {"recorded": 0}

    recorded = 0
    batch: dict = {}  # 批内去重：(source_type, source_id) → 记录对象（含本批新建），避免同批重复键触发唯一约束 500
    for item in req.items:
        if not item.question or not item.correct_answer:
            continue

        key = (item.source_type, item.source_id)
        if key not in batch:
            batch[key] = db.query(StudyError).filter(
                StudyError.user_id == req.user_id,
                StudyError.source_type == key[0],
                StudyError.source_id == key[1],
            ).first()
        existing = batch[key]

        if existing:
            # 已掌握后再次答错：重新激活（连击清零，闭环重新开始）
            existing.is_mastered = False
            existing.mastered_at = None
            existing.correct_streak = 0
            existing.error_count += 1
            existing.user_answer = item.user_answer
            existing.question = item.question
            existing.correct_answer = item.correct_answer
            existing.explanation = item.explanation
            if item.cause:
                existing.cause = item.cause
            if item.module_name:
                existing.module_name = item.module_name
            existing.wrong_at = date.today()
        else:
            rec = StudyError(
                user_id=req.user_id,
                source_type=item.source_type,
                source_id=item.source_id,
                module_name=item.module_name,
                question=item.question,
                user_answer=item.user_answer,
                correct_answer=item.correct_answer,
                explanation=item.explanation,
                cause=item.cause,
                error_count=1,
                wrong_at=date.today(),
            )
            db.add(rec)
            batch[key] = rec
        recorded += 1

    db.commit()
    return {"recorded": recorded}


@router.get("/errors", summary="查询学习错题列表")
def list_study_errors(
    user_id: str = Query(..., description="用户名"),
    source_type: Optional[str] = Query(None, description="过滤来源: grammar/classical"),
    subject: Optional[str] = Query(None, description="学科筛选: 英语→语法错题, 语文→古诗文错题, 数学→无学习错题"),
    only_pending: bool = Query(False, description="只看未掌握"),
    limit: int = Query(200, ge=1, le=500, description="单次返回上限，避免错题过多时一次性全量返回拖垮前端渲染"),
    db: Session = Depends(get_db),
):
    """查询学习错题列表，支持按学科(英语/语文/其他)与来源(grammar/classical)过滤、只看未掌握。

    参数（Query）：user_id、subject、source_type、only_pending、limit。
    返回：错题数组（含 id/来源/题目/正误答案/错因/error_count/is_mastered/wrong_at）。
    副作用：无（只读）。无需家长密码。
    性能：原实现用 .all() 全量返回，用户错题多时一次性渲染几百个节点会卡顿；
          现加 limit（默认 200）上限，前端配合「查看全部」按需加载。
    """
    q = db.query(StudyError).filter(StudyError.user_id == user_id)
    if subject:
        if subject == "英语":
            q = q.filter(StudyError.source_type.in_(["grammar", "vocab"]))
        elif subject == "语文":
            q = q.filter(StudyError.source_type == "classical")
        else:  # 学习错题仅来自英语语法/单词听写/语文古诗文，数学学科无学习错题
            q = q.filter(StudyError.id == -1)
    if source_type:
        q = q.filter(StudyError.source_type == source_type)
    if only_pending:
        q = q.filter(StudyError.is_mastered == False)  # noqa: E712
    errors = q.order_by(StudyError.wrong_at.desc(), StudyError.id.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "source_type": e.source_type,
            "module_name": e.module_name or ({"grammar": "语法练习", "vocab": "单词听写"}.get(e.source_type, "古诗文默写")),
            "question": e.question,
            "user_answer": e.user_answer,
            "correct_answer": e.correct_answer,
            "explanation": e.explanation,
            "error_count": e.error_count,
            "is_mastered": e.is_mastered,
            "cause": e.cause or "",
            "wrong_at": str(e.wrong_at) if e.wrong_at else "",
        }
        for e in errors
    ]


@router.post("/errors/master", summary="标记学习错题已掌握")
def mark_study_error_mastered(req: StudyErrorMasterRequest, db: Session = Depends(get_db)):
    """标记一条学习错题已掌握（mastered_at 置今天）。

    参数（Body）：user_id、error_id。
    返回：{ok: True}；记录不存在返回 404。
    副作用：置 is_mastered=True、并发放金币 +3（错题掌握）。无需家长密码。
    """
    error = db.query(StudyError).filter(
        StudyError.id == req.error_id,
        StudyError.user_id == req.user_id,
    ).first()
    if not error:
        raise HTTPException(404, "错题记录不存在")
    error.is_mastered = True
    error.mastered_at = date.today()
    # 错题掌握 → 金币 +3（P2 金币宠物）
    try:
        from app.domains.engagement.contracts import PetService
        PetService.grant_coins(db, req.user_id, 3, "错题掌握")
    except Exception:
        pass
    db.commit()
    return {"ok": True}


__all__ = [
    "StudyErrorItem", "StudyErrorRecordRequest", "StudyErrorMasterRequest",
    "record_study_errors", "list_study_errors", "mark_study_error_mastered",
]
