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
APPEAL_DAILY_LIMIT = 50  # 次/日/用户（防反复申诉抬分）


class AppealCreateReq(BaseModel):
    user_id: str
    source: str = "exam"          # exam=在线做题 / retry=错题重练
    question_id: int | None = None
    attempt_id: int | None = None  # exam：做题记录 id（交卷返回的 attempt_id，精确改判定位）
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
    note: str = ""  # 家长裁决备注（可选）


@router.post("/create", summary="孩子发起申诉（判错的题标记「我做对了」）")
def create_appeal(req: AppealCreateReq, db: Session = Depends(get_db)):
    """孩子发起申诉（判错的题标记「我做对了」）。

    请求：{user_id, source=exam/retry, question, user_answer, correct_answer, 可选 question_id/record_id 等}；无需家长密码。
    返回：{id, status, dup}（dup=true 表示同题同作答已存在 pending 申诉，直接复用）。
    副作用：限频 20 次/小时 + 5 次/日（防刷屏/防反复抬分）；写 answer_appeals（status=pending）。
            同用户+同作答+未处理的同 source 申诉去重，避免孩子刷屏。
    """
    q_text = (req.question or "").strip()
    ua = (req.user_answer or "").strip()
    if not q_text or not ua:
        raise HTTPException(400, "缺少题目或作答内容")
    if req.source not in ("exam", "retry"):
        raise HTTPException(400, "source 仅支持 exam / retry")
    if not rate_limit(f"appeal:{req.user_id}", APPEAL_LIMIT, APPEAL_LIMIT_WIN):
        raise HTTPException(429, "申诉提交太频繁啦，歇一歇再来")

    # 每日限额：防反复申诉抬分（DB 计数今日申诉数）
    from datetime import date
    day_start = datetime.combine(date.today(), datetime.min.time())
    today_cnt = db.query(AnswerAppeal).filter(
        AnswerAppeal.user_id == req.user_id,
        AnswerAppeal.created_at >= day_start,
    ).count()
    if today_cnt >= APPEAL_DAILY_LIMIT:
        raise HTTPException(429, f"今日申诉次数已达上限（{APPEAL_DAILY_LIMIT} 次），请明天再来")

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
        attempt_id=req.attempt_id,
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
                 limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    """申诉列表（家长面板待处理 / 历史）。

    查询参数：user_id, status（默认 pending；approved/rejected 查单一状态；history 查已裁决 approved+rejected）；无需家长密码。
    返回：{appeals:[{id, source, question_id/record_id, question, user_answer, correct_answer, status, created_at, decided_at}]}。
    副作用：只读，无写库。
    """
    q = db.query(AnswerAppeal).filter(AnswerAppeal.user_id == user_id)
    if status == "history":
        # 已裁决（家长已判对/判错），用于首页「家长反馈」区展示结果
        q = q.filter(AnswerAppeal.status.in_(["approved", "rejected"]))
    elif status:
        q = q.filter(AnswerAppeal.status == status)
    total = q.count()
    rows = q.order_by(AnswerAppeal.id.desc()).offset(offset).limit(min(limit, 200)).all()
    return {"appeals": [{
        "id": a.id,
        "source": a.source,
        "question_id": a.question_id,
        "attempt_id": a.attempt_id,
        "record_id": a.record_id,
        "record_kind": a.record_kind,
        "question": a.question,
        "user_answer": a.user_answer,
        "correct_answer": a.correct_answer,
        "subject": a.subject,
        "status": a.status,
        "created_at": str(a.created_at)[:16] if a.created_at else "",
        "decided_at": str(a.decided_at)[:16] if a.decided_at else "",
        "note": a.note or "",
    } for a in rows], "total": total}


@router.post("/decide", summary="家长二次确认：确认做对了（改判）/ 维持判错")
def decide_appeal(req: AppealDecideReq, db: Session = Depends(get_db)):
    """家长二次确认：确认做对了（改判）/ 维持判错。

    请求：{user_id, appeal_id, action=approve/reject}；无需家长密码（家长面板直接操作）。
    返回：{id, status}（approved/rejected）。
    副作用（仅 approve）：exam 源定位最新判错记录改判正确并重算本卷得分、删除本次新建错题痕迹；
            retry 源错题记录 correct_streak+1，累计达 3 次（MASTER_STREAK）自动标记掌握。
    幂等保证：用行锁（FOR UPDATE）串行化并发裁决，已裁决的申诉重复提交不再改分，避免重复点击抬分。
    """
    if req.action not in ("approve", "reject"):
        raise HTTPException(400, "action 仅支持 approve / reject")
    # 行锁：串行化对同一申诉的并发裁决，杜绝「20 次连点期间全部读到 pending 后重复加分」
    a = db.query(AnswerAppeal).with_for_update().filter(
        AnswerAppeal.id == req.appeal_id,
        AnswerAppeal.user_id == req.user_id,
    ).first()
    if not a:
        raise HTTPException(404, "申诉不存在")
    if a.status != "pending":
        # 已裁决：允许家长补填/修改备注，但不改变裁决结果（避免重复处理、也不翻转判对/判错）。
        note = (req.note or "").strip()
        if note:
            a.note = note[:500]
            db.commit()
        return {"id": a.id, "status": a.status, "already_decided": True}

    credited = True
    if req.action == "approve":
        if a.source == "exam":
            credited = _approve_exam(db, a)
        elif a.source == "retry":
            _approve_retry(db, a)
        else:
            raise HTTPException(400, "未知申诉类型")

    a.status = "approved" if req.action == "approve" else "rejected"
    a.decided_at = datetime.now()
    a.note = (req.note or "").strip()[:500]
    db.commit()
    note = "" if credited else "未找到对应做题记录，已直接批准申诉（仅清理错题标记，无卷面可改判）"
    return {"id": a.id, "status": a.status, "credited": credited, "note": note}


def _approve_exam(db: Session, a: AnswerAppeal) -> bool:
    """在线做题改判：定位该题最新一条判错记录 → 改判正确 + 重算本卷得分。

    只撤销本次提交造成的错题痕迹：
    - 本次新建的错题记录（wrong_record_id + wrong_new）→ 删除
    - 历史错题记录（重新标错的）→ 不动（历史上确实错过）

    幂等：本卷 correct/wrong/score 一律从作答记录「全量重算」，而非增量 ±1。
    因此同一条申诉被重复 approve（含并发）也只会改判同一道题一次，不会产生重复加分。

    返回 True=找到做题记录并改判成功；False=未找到做题记录（AI 出题/每日练习等
    路径未落 attempt_answers），此时降级处理：仍批准申诉（家长已人工确认），
    仅清理本次错题痕迹，不报「找不到题目」卡死家长操作。
    """
    if a.question_id:
        answer = None
        if a.attempt_id:
            # 精确：该次做题记录（attempt_id）+ 题目 → 唯一定位该作答
            # （交卷返回的 attempt_id，前端在申诉时一并上报；无视作答文本差异）
            answer = (db.query(AttemptAnswer)
                      .filter(AttemptAnswer.attempt_id == a.attempt_id,
                              AttemptAnswer.question_id == a.question_id)
                      .first())
        if not answer:
            # 兼容旧申诉（未上报 attempt_id）：按 user_id+question_id 匹配判错记录
            base = (db.query(AttemptAnswer)
                    .join(ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id)
                    .filter(ExamAttempt.user_id == a.user_id,
                            AttemptAnswer.question_id == a.question_id,
                            AttemptAnswer.is_correct == False)  # noqa: E712
                    .order_by(AttemptAnswer.id.desc()))
            answer = base.filter(AttemptAnswer.user_answer == a.user_answer).first()
            if not answer:
                # 放宽：规范化后比对（容忍全角/半角、空格、标点差异）
                from app.services.answer_check import normalize_answer
                ua_norm = normalize_answer(a.user_answer or "")
                for cand in base.limit(50).all():
                    if normalize_answer(cand.user_answer or "") == ua_norm:
                        answer = cand
                        break
            if not answer:
                # 兜底：家长已人工确认孩子做对，直接改判该题最新一条判错记录
                answer = base.first()
        if answer:
            answer.is_correct = True
            # 项目 sessionmaker 关闭了 autoflush，必须先 flush 让上面的改判落到当前事务，
            # 否则下方「全量重算」的 count 看不到本事务内刚改判的 is_correct，导致分数算错。
            db.flush()

            attempt = db.get(ExamAttempt, answer.attempt_id)
            if attempt and attempt.total:
                # 关键点：从本卷所有作答重新统计，幂等（重复改判同一题不再 +1）
                correct = db.query(AttemptAnswer).filter(
                    AttemptAnswer.attempt_id == attempt.id,
                    AttemptAnswer.is_correct == True,  # noqa: E712
                ).count()
                wrong = db.query(AttemptAnswer).filter(
                    AttemptAnswer.attempt_id == attempt.id,
                    AttemptAnswer.is_correct == False,  # noqa: E712
                ).count()
                attempt.correct = correct
                attempt.wrong = wrong
                attempt.score = int(round(attempt.correct / attempt.total * 100, 1))

            # 撤销本次新建的错题记录（本就不是错题，删除）；重复执行时记录已删，自动跳过
            if a.wrong_record_id and a.wrong_new:
                rec = db.get(WrongRecord, a.wrong_record_id)
                if rec:
                    db.delete(rec)
            return True

    # 未找到做题记录（如 AI 出题/每日练习路径的作答不落 attempt_answers）：
    # 家长已人工确认孩子做对 → 降级批准：仍清理本次错题痕迹，不报错卡死。
    if a.wrong_record_id:
        rec = db.get(WrongRecord, a.wrong_record_id)
        if rec:
            db.delete(rec)
    return False


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
