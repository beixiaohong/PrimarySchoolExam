"""错题练习提交、错因自评相关端点与模型"""
from datetime import date, timedelta
from typing import List

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import router
from .common import CAUSE_LABELS
from app.database import get_db
from app.models.study_error import StudyError
from app.models.exam import WrongRecord, Question


MASTER_STREAK = 3  # 单题累计答对 3 次（或修正模式整组全对）即判定为已掌握


class PracticeSubmitItem(BaseModel):
    """错题练习单条提交项：错题类型/记录 ID/是否答对/题目 ID，及 AI 复核与整组判定所需字段。"""
    kind: str  # exam / study
    record_id: int
    correct: bool
    qid: int = 0  # 题目 id（exam=Question.id）；后端以此重判，不信任前端 correct
    # ── AI 判题复核字段（本地判错的题需携带，供 AI 复核改判） ──
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    subject: str = ""
    batch: bool = False  # 专项错题：整组（如每词4题）视为「一次」尝试，用于背诵检测混入的错题


class PracticeSubmitRequest(BaseModel):
    """错题练习批量提交请求体：含用户标识与一组练习结果条目。"""
    user_id: str
    results: List[PracticeSubmitItem]


@router.post("/practice-submit", summary="错题练习提交（整组全对直接掌握 / 单题累计 3 次掌握）")
def practice_submit(req: PracticeSubmitRequest, db: Session = Depends(get_db)):
    """错题练习结果回写（双轨统一，按 record_id 分组判定）：

    - 修正模式（同一 record_id 提交 ≥3 条）：整组全对 → 直接标记已掌握；
      组内任一条答错 → 整组失败（streak 清零、计数 +1、重新激活）
    - 兼容旧模式（单条提交）：答对 streak +1，累计 3 次掌握；答错清零重激活
    - AI 判题复核：本地判错且带作答内容的题批量送 AI，AI 判对 → 该条视为答对再分组
    """
    from datetime import datetime as _dt
    from collections import defaultdict

    # ── 防刷：exam 类题以后端重判为准（不信任前端 correct，避免看答案抄写刷掌握） ──
    exam_qids = [it.qid for it in req.results if it.kind == "exam" and it.qid]
    if exam_qids:
        from app.domains.assessment.contracts import _check_answer as _exam_check
        q_map = {q.id: q for q in db.query(Question).filter(Question.id.in_(exam_qids)).all()}
        for it in req.results:
            if it.kind == "exam" and it.qid in q_map:
                q = q_map[it.qid]
                it.correct = _exam_check(it.user_answer or "", (q.answer or "").strip(), q.options_json)

    # ── AI 判题复核（只升不降）：本地判错的题批量送 AI，AI 判对 → 改判正确 ──
    ai_approved: list = []
    ai_items = [
        {"key": i, "question": it.question, "answer": it.correct_answer,
         "user_answer": it.user_answer, "subject": it.subject}
        for i, it in enumerate(req.results)
        if not it.correct and (it.question or it.user_answer) and not it.batch
    ]
    if ai_items:
        from app.domains.assessment.contracts import judge_wrong_items
        approved = judge_wrong_items(req.user_id, ai_items)
        for i, it in enumerate(req.results):
            if i in approved and approved[i].get("correct"):
                it.correct = True
                ai_approved.append(i)

    # AI 已判对的题：同步自动确认孩子对同错题记录的待处理申诉（避免家长端重复确认）
    if ai_approved:
        from app.models.appeal import AnswerAppeal
        from datetime import datetime as _dt
        auto_map = {req.results[i].record_id: req.results[i].user_answer for i in ai_approved}
        auto = db.query(AnswerAppeal).filter(
            AnswerAppeal.user_id == req.user_id,
            AnswerAppeal.status == "pending",
            AnswerAppeal.source == "retry",
            AnswerAppeal.record_id.in_(auto_map.keys()),
        ).all()
        for ap in auto:
            if auto_map.get(ap.record_id) == ap.user_answer:
                ap.status = "approved"
                ap.decided_at = _dt.now()

    updated = []
    groups = defaultdict(list)
    for item in req.results:
        groups[(item.kind, item.record_id)].append(item)

    for (kind, rid), items in groups.items():
        all_correct = all(it.correct for it in items)
        if kind == "exam":
            rec = db.query(WrongRecord).filter(
                WrongRecord.id == rid,
                WrongRecord.user_id == req.user_id,
            ).first()
            if not rec:
                continue
            if rec.is_unanswered:
                continue  # 未作答的题不走修正流程，需先通过 answer-unanswered 作答
            if len(items) >= 3:
                # 修正模式：整组判定（三道同类型全对才算修正）
                if all_correct:
                    rec.correct_streak = max(rec.correct_streak, MASTER_STREAK)
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.correct_streak = 0
                    rec.practice_count += 1
                    rec.is_mastered = False
                    rec.mastered_at = None
                    rec.wrong_at = _dt.now()
                    rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                    status = "reactivated"
            elif items[0].correct:
                rec.correct_streak = rec.correct_streak + 1
                if rec.correct_streak >= MASTER_STREAK:
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.next_review_date = None   # 答对即出队（明日复习队列只留「重做仍错」）
                    status = "streak"
            else:
                rec.correct_streak = 0
                rec.practice_count += 1
                rec.is_mastered = False
                rec.mastered_at = None
                rec.wrong_at = _dt.now()
                rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                status = "reactivated"
            updated.append({"kind": "exam", "record_id": rec.id,
                            "status": status, "streak": rec.correct_streak})
        elif kind == "study":
            rec = db.query(StudyError).filter(
                StudyError.id == rid,
                StudyError.user_id == req.user_id,
            ).first()
            if not rec:
                continue
            if getattr(items[0], "batch", False):
                # 专项错题：整组（如每词4题）视为「一次」尝试，用于背诵检测混入的错题
                # 全对 → 连击 +1（满 3 掌握）；任一错 → 连击清零、重激活
                all_correct = all(it.correct for it in items)
                if all_correct:
                    rec.correct_streak += 1
                    if rec.correct_streak >= MASTER_STREAK:
                        rec.is_mastered = True
                        rec.mastered_at = _dt.now()
                        rec.next_review_date = None
                        status = "mastered"
                    else:
                        rec.next_review_date = None   # 答对即出队（明日复习队列只留「重做仍错」）
                        status = "streak"
                else:
                    rec.correct_streak = 0
                    rec.error_count += 1
                    rec.is_mastered = False
                    rec.mastered_at = None
                    rec.wrong_at = _dt.now()
                    rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                    status = "reactivated"
            elif len(items) >= 3:
                # 修正模式：整组判定
                if all_correct:
                    rec.correct_streak = max(rec.correct_streak, MASTER_STREAK)
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.correct_streak = 0
                    rec.error_count += 1
                    rec.is_mastered = False
                    rec.mastered_at = None
                    rec.wrong_at = _dt.now()
                    rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                    status = "reactivated"
            elif items[0].correct:
                rec.correct_streak = rec.correct_streak + 1
                if rec.correct_streak >= MASTER_STREAK:
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.next_review_date = None   # 答对即出队（明日复习队列只留「重做仍错」）
                    status = "streak"
            else:
                rec.correct_streak = 0
                rec.error_count += 1
                rec.is_mastered = False
                rec.mastered_at = None
                rec.wrong_at = _dt.now()
                rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                status = "reactivated"
            updated.append({"kind": "study", "record_id": rec.id,
                            "status": status, "streak": rec.correct_streak})

    # 重做掌握 → 金币 +3（P2 金币宠物）
    try:
        from app.domains.engagement.contracts import _grant_coins
        if any(u["status"] == "mastered" for u in updated):
            _grant_coins(db, req.user_id, 3 * sum(1 for u in updated if u["status"] == "mastered"), "错题掌握")
    except Exception:
        pass
    db.commit()
    return {"updated": len(updated), "details": updated, "ai_approved": ai_approved}


class CauseRequest(BaseModel):
    """错因自评请求体：针对一条错题记录（exam 试卷错题 / study 学习错题）标注错因。"""
    user_id: str
    kind: str  # exam / study
    record_id: int
    cause: str


@router.post("/cause", summary="提交错因自评")
def submit_cause(req: CauseRequest, db: Session = Depends(get_db)):
    """为一条错题记录标注错因（四选一），exam 指试卷错题，study 指学习错题"""
    if req.cause not in CAUSE_LABELS:
        raise HTTPException(400, f"错因无效，可选：{', '.join(CAUSE_LABELS.keys())}")

    if req.kind == "exam":
        rec = db.query(WrongRecord).filter(
            WrongRecord.id == req.record_id,
            WrongRecord.user_id == req.user_id,
        ).first()
    elif req.kind == "study":
        rec = db.query(StudyError).filter(
            StudyError.id == req.record_id,
            StudyError.user_id == req.user_id,
        ).first()
    else:
        raise HTTPException(400, "kind 仅支持 exam / study")

    if not rec:
        raise HTTPException(404, "错题记录不存在")

    rec.cause = req.cause
    db.commit()
    return {"ok": True, "cause": req.cause, "cause_label": CAUSE_LABELS[req.cause]}


class CauseByQuestionRequest(BaseModel):
    """按题目提交错因自评请求体：针对试卷错题按 question_id 标注错因（答题中自评）。"""
    user_id: str
    question_id: int
    cause: str


@router.post("/cause-by-question", summary="按题目提交错因自评（答题中自评）")
def submit_cause_by_question(req: CauseByQuestionRequest, db: Session = Depends(get_db)):
    """试卷错题按 question_id 提交错因（答题完成后批量调用）"""
    if req.cause not in CAUSE_LABELS:
        raise HTTPException(400, f"错因无效，可选：{', '.join(CAUSE_LABELS.keys())}")
    rec = db.query(WrongRecord).filter(
        WrongRecord.user_id == req.user_id,
        WrongRecord.question_id == req.question_id,
    ).order_by(WrongRecord.id.desc()).first()
    if not rec:
        raise HTTPException(404, "该题暂不在错题本中")
    rec.cause = req.cause
    db.commit()
    return {"ok": True, "cause": req.cause, "cause_label": CAUSE_LABELS[req.cause]}


__all__ = [
    "MASTER_STREAK", "PracticeSubmitItem", "PracticeSubmitRequest",
    "practice_submit", "CauseRequest", "submit_cause",
    "CauseByQuestionRequest", "submit_cause_by_question",
]
