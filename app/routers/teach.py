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


@router.post("/create", summary="从错题出一道「讲给家长」的题（同时只教 1 道）")
def create_card(req: CreateReq, db: Session = Depends(get_db)):
    from ..models.sprint4 import TeachingRecord
    active = db.query(TeachingRecord).filter(
        TeachingRecord.user_id == req.user_id,
        TeachingRecord.status.in_(ACTIVE_STATUS),
    ).first()
    if active:
        raise HTTPException(400, "还有一道题在教家长，先讲完再出下一道")
    question, answer = _source(db, req.user_id, req.kind, req.record_id)
    c = TeachingRecord(user_id=req.user_id, record_kind=req.kind,
                       record_id=req.record_id, question=question,
                       answer=answer, status="pending")
    db.add(c)
    db.commit()
    return _card_out(c)


@router.get("/active", summary="当前在教的题（待作答/待批改）")
def get_active(user_id: str = Query(...), db: Session = Depends(get_db)):
    from ..models.sprint4 import TeachingRecord
    c = db.query(TeachingRecord).filter(
        TeachingRecord.user_id == user_id,
        TeachingRecord.status.in_(ACTIVE_STATUS),
    ).order_by(TeachingRecord.id.desc()).first()
    return {"card": _card_out(c) if c else None}


@router.post("/answer", summary="「家长」作答")
def submit_answer(req: AnswerReq, db: Session = Depends(get_db)):
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
    else:
        c.status = "pending"  # 没讲明白，重新讲
        c.answer_text = ""
    db.commit()
    return _card_out(c)


@router.get("/due", summary="7 天到期待复习验证的题")
def get_due(user_id: str = Query(...), db: Session = Depends(get_db)):
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
    from ..models.sprint4 import TeachingRecord
    rows = db.query(TeachingRecord).filter(TeachingRecord.user_id == user_id).all()
    return {
        "total": len(rows),
        "passed": sum(1 for r in rows if r.recheck_status == "passed"),
        "teaching": sum(1 for r in rows if r.status in ACTIVE_STATUS),
    }
