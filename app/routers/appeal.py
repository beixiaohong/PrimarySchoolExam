"""孩子申诉：批改判错 → 孩子「我做对了」→ 家长二次确认（013 迁移建表）

流程：
1. 孩子作答被判错（AI 复核后仍判错）→ 反馈区点「我做对了」→ POST /create 创建申诉
2. 家长在「设置-家长管理」看到待处理申诉 → 确认做对了（approve）或维持判错（reject）
3. approve 处理：
   - exam（在线做题）：定位该题最新一条判错记录（AttemptAnswer）→ 改判正确、
     重算本卷得分（正确数/分数），本次新建的错题记录删除、历史记录不动
   - retry（错题重练）：对应错题记录正确连击 +1，累计 3 次自动掌握
4. 同题同作答的 pending 申诉去重，防孩子刷屏
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.appeal import AnswerAppeal
from ..models.exam import AttemptAnswer, ExamAttempt, WrongRecord
from ..services.ai import rate_limit

router = APIRouter()

APPEAL_LIMIT = 20  # 次/小时/用户（防刷屏）
APPEAL_LIMIT_WIN = 3600


class AppealCreateReq(BaseModel):
    user_id: str
    source: str = "exam"          # exam=在线做题 / retry=错题重练
    question_id: int | None = None
    record_id: int | None = None   # retry：错题记录 id
    record_kind: str | None = None  # retry：exam / study
    question: str
    user_answer: str
    correct_answer: str
    subject: str = ""
    wrong_record_id: int | None = None  # exam：本次提交新建的错题记录（确认后删除）
    wrong_new: bool = False


class AppealDecideReq(BaseModel):
    user_id: str
    appeal_id: int
    action: str  # approve / reject


@router.post("/create", summary="孩子发起申诉（判错的题标记「我做对了」）")
def create_appeal(req: AppealCreateReq, db: Session = Depends(get_db)):
    q_text = (req.question or "").strip()
    ua = (req.user_answer or "").strip()
    if not q_text or not ua:
        raise HTTPException(400, "缺少题目或作答内容")
    if req.source not in ("exam", "retry"):
        raise HTTPException(400, "source 仅支持 exam / retry")
    if not rate_limit(f"appeal:{req.user_id}", APPEAL_LIMIT, APPEAL_LIMIT_WIN):
        raise HTTPException(429, "申诉提交太频繁啦，歇一歇再来")

    # 去重：同题同作答且未处理 → 返回已有申诉
    dup = db.query(AnswerAppeal).filter(
        AnswerAppeal.user_id == req.user_id,
        AnswerAppeal.status == "pending",
        AnswerAppeal.user_answer == ua,
    )
    if req.source == "exam":
        dup = dup.filter(AnswerAppeal.question_id == (req.question_id or -1))
    else:
        dup = dup.filter(AnswerAppeal.record_id == (req.record_id or -1))
    existing = dup.first()
    if existing:
        return {"id": existing.id, "status": existing.status, "dup": True}

    a = AnswerAppeal(
        user_id=req.user_id,
        source=req.source,
        question_id=req.question_id,
        record_id=req.record_id,
        record_kind=req.record_kind,
        question=q_text[:1000],
        user_answer=ua[:1000],
        correct_answer=(req.correct_answer or "").strip()[:1000],
        subject=(req.subject or "")[:20],
        wrong_record_id=req.wrong_record_id,
        wrong_new=bool(req.wrong_new),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "status": a.status, "dup": False}


@router.get("/list", summary="申诉列表（家长面板待处理 / 历史）")
def list_appeals(user_id: str, status: str = "pending",
                 limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(AnswerAppeal).filter(AnswerAppeal.user_id == user_id)
    if status:
        q = q.filter(AnswerAppeal.status == status)
    rows = q.order_by(AnswerAppeal.id.desc()).limit(min(limit, 100)).all()
    return {"appeals": [{
        "id": a.id,
        "source": a.source,
        "question_id": a.question_id,
        "record_id": a.record_id,
        "record_kind": a.record_kind,
        "question": a.question,
        "user_answer": a.user_answer,
        "correct_answer": a.correct_answer,
        "subject": a.subject,
        "status": a.status,
        "created_at": str(a.created_at)[:16] if a.created_at else "",
    } for a in rows]}


@router.post("/decide", summary="家长二次确认：确认做对了（改判）/ 维持判错")
def decide_appeal(req: AppealDecideReq, db: Session = Depends(get_db)):
    if req.action not in ("approve", "reject"):
        raise HTTPException(400, "action 仅支持 approve / reject")
    a = db.query(AnswerAppeal).filter(
        AnswerAppeal.id == req.appeal_id,
        AnswerAppeal.user_id == req.user_id,
    ).first()
    if not a:
        raise HTTPException(404, "申诉不存在")
    if a.status != "pending":
        raise HTTPException(400, "该申诉已处理过")

    if req.action == "approve":
        if a.source == "exam":
            _approve_exam(db, a)
        elif a.source == "retry":
            _approve_retry(db, a)
        else:
            raise HTTPException(400, "未知申诉类型")

    a.status = "approved" if req.action == "approve" else "rejected"
    a.decided_at = datetime.now()
    db.commit()
    return {"id": a.id, "status": a.status}


def _approve_exam(db: Session, a: AnswerAppeal):
    """在线做题改判：定位该题最新一条判错记录 → 改判正确 + 重算本卷得分。

    只撤销本次提交造成的错题痕迹：
    - 本次新建的错题记录（wrong_record_id + wrong_new）→ 删除
    - 历史错题记录（重新标错的）→ 不动（历史上确实错过）
    """
    if not a.question_id:
        raise HTTPException(400, "申诉缺少题目信息，无法改判")
    # 找该题最新一条「判错且作答相同」的记录（孩子提交后作答内容一致）
    answer = (db.query(AttemptAnswer)
              .join(ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id)
              .filter(ExamAttempt.user_id == a.user_id,
                      AttemptAnswer.question_id == a.question_id,
                      AttemptAnswer.is_correct == False,  # noqa: E712
                      AttemptAnswer.user_answer == a.user_answer)
              .order_by(AttemptAnswer.id.desc()).first())
    if not answer:
        raise HTTPException(400, "找不到对应的做题记录，无法改判（可维持判错）")
    answer.is_correct = True

    attempt = db.query(ExamAttempt).get(answer.attempt_id)
    if attempt and attempt.total:
        attempt.correct = (attempt.correct or 0) + 1
        attempt.wrong = max(0, (attempt.wrong or 0) - 1)
        attempt.score = int(round(attempt.correct / attempt.total * 100, 1))

    # 撤销本次新建的错题记录（本就不是错题，删除）
    if a.wrong_record_id and a.wrong_new:
        rec = db.query(WrongRecord).get(a.wrong_record_id)
        if rec:
            db.delete(rec)


def _approve_retry(db: Session, a: AnswerAppeal):
    """错题重练改判：该错题记录正确连击 +1（视为答对一次），累计 3 次自动掌握。"""
    if not a.record_id:
        raise HTTPException(400, "申诉缺少错题记录信息，无法改判")
    from .study import MASTER_STREAK
    if a.record_kind == "study":
        from ..models.study_error import StudyError
        rec = db.query(StudyError).filter(
            StudyError.id == a.record_id, StudyError.user_id == a.user_id).first()
        if not rec:
            raise HTTPException(404, "错题记录不存在")
        rec.correct_streak = (rec.correct_streak or 0) + 1
        if rec.correct_streak >= MASTER_STREAK:
            rec.is_mastered = True
            rec.mastered_at = datetime.now()
    else:
        rec = db.query(WrongRecord).filter(
            WrongRecord.id == a.record_id, WrongRecord.user_id == a.user_id).first()
        if not rec:
            raise HTTPException(404, "错题记录不存在")
        rec.correct_streak = (rec.correct_streak or 0) + 1
        if rec.correct_streak >= MASTER_STREAK:
            rec.is_mastered = True
            rec.mastered_at = datetime.now()
