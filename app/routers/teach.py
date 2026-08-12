"""小老师模式：错题出题给家长 → 家长作答 → 孩子批改 → 7 天复习验证

状态机（teaching_records.status）：
- pending（孩子讲解中，待"家长"作答）→ answered → graded（批改完成）
- 批改答错 → 重置 pending 重新讲解
- graded 后 due_date = 批改日 + 7 天，到期 recheck：通过 recheck_status=passed；
  失败则重置回 pending 重新讲解
同时只允许 1 道题在教（pending/answered）。
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter()

ACTIVE_STATUS = ("pending", "answered")
ACTIVE_LIMIT = 3  # PRD 17：孩子一次最多同时教 3 道错题（pending/answered 视为在教中）


class CreateReq(BaseModel):
    user_id: str
    kind: str  # exam / study（错题来源）
    record_id: int


class AnswerReq(BaseModel):
    user_id: str
    card_id: int
    answer_text: str = ""


class GradeReq(BaseModel):
    user_id: str
    card_id: int
    is_correct: bool


class RecheckReq(BaseModel):
    user_id: str
    card_id: int
    is_correct: bool


def _card_out(c):
    return {
        "id": c.id, "record_kind": c.record_kind, "record_id": c.record_id,
        "question": c.question, "answer": c.answer, "note": c.note,
        "status": c.status, "answer_text": c.answer_text,
        "is_correct": c.is_correct,
        "due_date": str(c.due_date) if c.due_date else None,
        "recheck_status": c.recheck_status,
    }


def _source(db: Session, user_id: str, kind: str, record_id: int):
    """取错题来源快照（exam=WrongRecord→Question，study=StudyError）"""
    if kind == "exam":
        from ..models.exam import Question, WrongRecord
        w = db.query(WrongRecord).filter(WrongRecord.id == record_id,
                                         WrongRecord.user_id == user_id).first()
        if not w:
            raise HTTPException(404, "错题不存在")
        q = db.query(Question).filter(Question.id == w.question_id).first()
        if not q:
            raise HTTPException(404, "题目内容缺失")
        return q.question, q.answer
    if kind == "study":
        from ..models.study_error import StudyError
        e = db.query(StudyError).filter(StudyError.id == record_id,
                                        StudyError.user_id == user_id).first()
        if not e:
            raise HTTPException(404, "错题不存在")
        return e.question, e.correct_answer
    raise HTTPException(400, "kind 只能是 exam/study")


@router.post("/create", summary="从错题出一道「讲给家长」的题（最多同时教 3 道）")
def create_card(req: CreateReq, db: Session = Depends(get_db)):
    """从一道错题出「讲给家长」的讲解卡（同一错题不可重复出，在教中上限 ACTIVE_LIMIT=3）。

    参数（Body）：user_id、kind（exam/study）、record_id。
    返回：讲解卡详情（_card_out）；超出数量/重复出/来源错误 返回 400/404。
    副作用：写 TeachingRecord（status=pending）。无需家长密码。
    """
    from ..models.sprint4 import TeachingRecord
    active_count = db.query(TeachingRecord).filter(
        TeachingRecord.user_id == req.user_id,
        TeachingRecord.status.in_(ACTIVE_STATUS),
    ).count()
    if active_count >= ACTIVE_LIMIT:
        raise HTTPException(400, f"最多同时教 {ACTIVE_LIMIT} 道题，先讲完再出下一道")
    dup = db.query(TeachingRecord).filter(
        TeachingRecord.user_id == req.user_id,
        TeachingRecord.status.in_(ACTIVE_STATUS),
        TeachingRecord.record_kind == req.kind,
        TeachingRecord.record_id == req.record_id,
    ).first()
    if dup:
        raise HTTPException(400, "这道题已经在教啦，去小老师课堂继续吧")
    question, answer = _source(db, req.user_id, req.kind, req.record_id)
    c = TeachingRecord(user_id=req.user_id, record_kind=req.kind,
                       record_id=req.record_id, question=question,
                       answer=answer, status="pending")
    db.add(c)
    db.commit()
    return _card_out(c)


@router.get("/active", summary="当前在教的题列表（待作答/待批改，最多 3 道）")
def get_active(user_id: str = Query(...), db: Session = Depends(get_db)):
    """返回当前在教的讲解卡列表（status ∈ pending/answered，最多 3 道）。

    参数（Query）：user_id。
    返回：{items[讲解卡详情]}。
    副作用：无（只读）。无需家长密码。
    """
    from ..models.sprint4 import TeachingRecord
    rows = db.query(TeachingRecord).filter(
        TeachingRecord.user_id == user_id,
        TeachingRecord.status.in_(ACTIVE_STATUS),
    ).order_by(TeachingRecord.id.asc()).all()
    return {"items": [_card_out(c) for c in rows]}


@router.post("/answer", summary="「家长」作答")
def submit_answer(req: AnswerReq, db: Session = Depends(get_db)):
    """「家长」作答讲解卡（pending → answered）。

    参数（Body）：user_id、card_id、answer_text。
    返回：讲解卡详情；卡片不存在 404、非 pending 状态 400。
    副作用：置 status=answered、记 answered_at。无需家长密码。
    """
    from datetime import datetime
    from ..models.sprint4 import TeachingRecord
    c = db.query(TeachingRecord).filter(TeachingRecord.id == req.card_id,
                                        TeachingRecord.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "讲解卡不存在")
    if c.status != "pending":
        raise HTTPException(400, "当前不需要作答")
    c.answer_text = (req.answer_text or "").strip()
    c.status = "answered"
    c.answered_at = datetime.now()
    db.commit()
    return _card_out(c)


@router.post("/grade", summary="孩子批改：答对 → 7 天后复习验证；答错 → 重新讲")
def grade_answer(req: GradeReq, db: Session = Depends(get_db)):
    """孩子批改：答对 → graded 并排 7 天后复习验证（due_date=批改日+7天，发金币+10）；
    答错 → 重置回 pending 重新讲（清空作答内容）。

    参数（Body）：user_id、card_id、is_correct。
    返回：讲解卡详情；卡片不存在 404、非 answered 状态 400。
    副作用：更新 TeachingRecord 状态机；答对发金币。无需家长密码。
    """
    from datetime import datetime
    from ..models.sprint4 import TeachingRecord
    c = db.query(TeachingRecord).filter(TeachingRecord.id == req.card_id,
                                        TeachingRecord.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "讲解卡不存在")
    if c.status != "answered":
        raise HTTPException(400, "还没有家长作答")
    if req.is_correct:
        c.is_correct = 1
        c.status = "graded"
        c.graded_at = datetime.now()
        c.due_date = date.today() + timedelta(days=7)
        c.recheck_status = None
        # 讲清楚 → 金币 +10（P2 金币宠物）
        try:
            from .pet import _grant_coins
            _grant_coins(db, req.user_id, 10, "小老师讲清楚")
        except Exception:
            pass
    else:
        c.status = "pending"  # 没讲明白，重新讲
        c.answer_text = ""
    db.commit()
    return _card_out(c)


@router.get("/due", summary="7 天到期待复习验证的题")
def get_due(user_id: str = Query(...), db: Session = Depends(get_db)):
    """返回 7 天到期待复习验证的讲解卡（graded 且 due_date<=今天 且未 recheck）。

    参数（Query）：user_id。
    返回：{items[讲解卡详情]}。
    副作用：无（只读）。无需家长密码。
    """
    from ..models.sprint4 import TeachingRecord
    rows = db.query(TeachingRecord).filter(
        TeachingRecord.user_id == user_id,
        TeachingRecord.status == "graded",
        TeachingRecord.due_date <= date.today(),
        TeachingRecord.recheck_status.is_(None),
    ).order_by(TeachingRecord.due_date.asc()).all()
    return {"items": [_card_out(c) for c in rows]}


@router.post("/recheck", summary="7 天复习验证：通过或重新讲")
def recheck(req: RecheckReq, db: Session = Depends(get_db)):
    """7 天复习验证：通过 → recheck_status=passed（闭环完成）；
    失败 → 重置回 pending 重新讲（清空作答/批改/due_date）。

    参数（Body）：user_id、card_id、is_correct。
    返回：讲解卡详情；卡片不存在 404、未到验证时间 400。
    副作用：更新 TeachingRecord 状态机。无需家长密码。
    """
    from datetime import datetime
    from ..models.sprint4 import TeachingRecord
    c = db.query(TeachingRecord).filter(TeachingRecord.id == req.card_id,
                                        TeachingRecord.user_id == req.user_id).first()
    if not c:
        raise HTTPException(404, "讲解卡不存在")
    if c.status != "graded" or c.due_date is None or c.due_date > date.today():
        raise HTTPException(400, "还没到复习验证时间")
    if req.is_correct:
        c.recheck_status = "passed"
    else:
        c.recheck_status = "failed"
        c.status = "pending"  # 忘了，重新讲一遍
        c.answer_text = ""
        c.answered_at = None
        c.graded_at = None
        c.is_correct = None
        c.due_date = None
    c.graded_at = datetime.now()
    db.commit()
    return _card_out(c)


@router.get("/stats", summary="小老师记录统计")
def get_stats(user_id: str = Query(...), db: Session = Depends(get_db)):
    """小老师记录统计：总题数 / 复习通过数 / 在教中题数。

    参数（Query）：user_id。
    返回：{total, passed, teaching}。
    副作用：无（只读）。无需家长密码。
    """
    from ..models.sprint4 import TeachingRecord
    rows = db.query(TeachingRecord).filter(TeachingRecord.user_id == user_id).all()
    return {
        "total": len(rows),
        "passed": sum(1 for r in rows if r.recheck_status == "passed"),
        "teaching": sum(1 for r in rows if r.status in ACTIVE_STATUS),
    }
