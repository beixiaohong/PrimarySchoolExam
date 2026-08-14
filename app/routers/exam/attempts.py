"""在线做题与做题记录查询端点"""
import json
from datetime import datetime

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import router
from .common import _check_answer
from app.database import get_db
from app.models.exam import (
    ExamRecord, Question, WrongRecord, ExamAttempt, AttemptAnswer,
)


@router.post("/submit-answers", summary="提交答案（在线做题判分）")
def submit_answers(req: dict, db: Session = Depends(get_db)):
    """
    在线做题提交。
    请求体: {
        "user_id": "小明",
        "exam_id": 1,
        "answers": [{"question_id": 1, "user_answer": "xxx"}, ...]
    }
    返回: 每题对错 + 总分 + 自动将错题加入错题本
    """
    user_id = req.get("user_id", "")
    exam_id = req.get("exam_id")
    answers = req.get("answers", [])

    if not isinstance(answers, list):
        raise HTTPException(400, "answers 必须是数组")
    if not user_id or not exam_id or not answers:
        raise HTTPException(400, "缺少 user_id / exam_id / answers")

    # 防刷：提交耗时过短判为无效（每题至少 3 秒；未上报时长时不拦截，兼容旧前端）
    duration = req.get("duration_sec") or 0
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0
    if duration > 0 and duration < len(answers) * 3:
        raise HTTPException(400, "提交太快啦，认真做完再交卷哦")

    record = db.query(ExamRecord).get(exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")

    now = datetime.now()
    results = []
    correct_count = 0
    wrong_seqs = []
    wrong_ids: dict = {}
    wrong_new_ids: dict = {}     # 本次新建的错题记录 {qid: record_id}（供申诉撤销）
    prev_states: dict = {}       # 本次被重新标错的旧记录 {qid: 快照}（AI 判对时恢复）
    ai_items = []                # 本地判错 → 送 AI 复核

    for item in answers:
        qid = item.get("question_id")
        user_ans = str(item.get("user_answer", "")).strip()
        q = db.query(Question).filter(Question.id == qid, Question.exam_id == exam_id).first()
        if not q:
            continue

        # 判分：选择题精确匹配，其他去空格后包含匹配
        correct_ans = q.answer.strip()
        is_correct = _check_answer(user_ans, correct_ans, q.options_json)

        if is_correct:
            correct_count += 1
        else:
            wrong_seqs.append(q.seq)
            # 自动加入错题本
            existing = db.query(WrongRecord).filter(
                WrongRecord.user_id == user_id,
                WrongRecord.question_id == q.id,
            ).first()
            if existing:
                prev_states[q.id] = {
                    "is_mastered": existing.is_mastered,
                    "mastered_at": existing.mastered_at,
                    "correct_streak": existing.correct_streak,
                    "wrong_at": existing.wrong_at,
                    "is_unanswered": existing.is_unanswered,
                }
                existing.is_mastered = False
                existing.mastered_at = None
                existing.correct_streak = 0  # 重新标错：连击清零，闭环重新开始
                existing.is_unanswered = not user_ans
                existing.wrong_at = now
                wrong_ids[q.id] = existing.id
            else:
                rec = WrongRecord(
                    user_id=user_id, question_id=q.id,
                    is_unanswered=not user_ans, wrong_at=now,
                )
                db.add(rec)
                db.flush()  # 立即取得 id，供前端错因自评
                wrong_ids[q.id] = rec.id
                wrong_new_ids[q.id] = rec.id

            # 送 AI 复核（只升不降：AI 判对 → 改判正确）
            options = []
            if q.options_json:
                try:
                    parsed = json.loads(q.options_json)
                    options = parsed if isinstance(parsed, list) else []
                except (ValueError, TypeError):
                    options = []
            ai_items.append({
                "key": q.id,
                "question_id": q.id,
                "question": q.question,
                "answer": correct_ans,
                "user_answer": user_ans,
                "subject": q.subject,
                "options": options,
            })

        results.append({
            "question_id": q.id,
            "seq": q.seq,
            "question": q.question,
            # 防刷：错题不回传正确答案（避免重做背答案刷满分），订正走错题本
            "correct_answer": correct_ans if is_correct else "",
            "user_answer": user_ans,
            "is_correct": is_correct,
        })

    # ── AI 判题复核：本地判错的题批量送 AI，AI 判对 → 改判正确 ──
    ai_approved: list = []
    if ai_items:
        from app.services.judge import judge_wrong_items
        approved = judge_wrong_items(user_id, ai_items)
        for r in results:
            qid = r["question_id"]
            if r["is_correct"] or qid not in approved:
                continue
            # 改判正确：得分回补、撤销本次错题处理
            r["is_correct"] = True
            correct_count += 1
            if r["seq"] in wrong_seqs:
                wrong_seqs.remove(r["seq"])
            if qid in wrong_new_ids:
                rec = db.query(WrongRecord).get(wrong_new_ids[qid])
                if rec:
                    db.delete(rec)  # 本次新建的记录：本就不是错题，删除
                wrong_ids.pop(qid, None)
                wrong_new_ids.pop(qid, None)
            elif qid in prev_states:
                rec = db.query(WrongRecord).get(wrong_ids.get(qid))
                if rec:
                    st = prev_states[qid]  # 恢复历史记录（撤销本次重新标错）
                    rec.is_mastered = st["is_mastered"]
                    rec.mastered_at = st["mastered_at"]
                    rec.correct_streak = st["correct_streak"]
                    rec.wrong_at = st["wrong_at"]
                wrong_ids.pop(qid, None)
            ai_approved.append(qid)

    # AI 已判对的题：同步自动确认孩子对同题的待处理申诉（避免家长端重复确认）
    if ai_approved:
        from app.models.appeal import AnswerAppeal
        ans_map = {r["question_id"]: r["user_answer"] for r in results}
        auto = db.query(AnswerAppeal).filter(
            AnswerAppeal.user_id == user_id,
            AnswerAppeal.status == "pending",
            AnswerAppeal.source == "exam",
            AnswerAppeal.question_id.in_(ai_approved),
        ).all()
        for ap in auto:
            if ans_map.get(ap.question_id) == ap.user_answer:
                ap.status = "approved"
                ap.decided_at = now

    db.commit()

    total = len(results)
    score = round(correct_count / total * 100, 1) if total > 0 else 0

    # 保存做题记录
    attempt = ExamAttempt(
        user_id=user_id,
        exam_id=exam_id,
        score=int(score),
        total=total,
        correct=correct_count,
        wrong=total - correct_count,
        duration_sec=req.get("duration_sec", 0),
    )
    db.add(attempt)
    db.flush()

    for r in results:
        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=r["question_id"],
            user_answer=r["user_answer"],
            is_correct=r["is_correct"],
        ))
    # 答题发金币：每题答对 +1，全对额外 +10（P2 金币宠物）
    try:
        from app.routers.pet import _grant_coins
        if correct_count > 0:
            _grant_coins(db, user_id, correct_count, "答题答对")
        if total > 0 and correct_count == total:
            _grant_coins(db, user_id, 10, "全对奖励")
    except Exception:
        pass
    db.commit()

    return {
        "exam_id": exam_id,
        "attempt_id": attempt.id,
        "user_id": user_id,
        "total": total,
        "correct": correct_count,
        "wrong": total - correct_count,
        "score": score,
        "results": results,
        "wrong_ids": wrong_ids,
        "wrong_new_ids": wrong_new_ids,
        "ai_reviewed": len(ai_items),
        "ai_approved": ai_approved,
    }


@router.get("/attempts/list", summary="用户做题记录列表")
def list_attempts(
    user_id: str = Query(..., description="用户标识"),
    subject: str = Query(None, description="学科筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(ExamAttempt).filter(ExamAttempt.user_id == user_id)
    if subject:
        q = q.join(ExamRecord).filter(ExamRecord.subject == subject)
    attempts = q.order_by(ExamAttempt.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    # 批量取试卷标题与学科，避免 N+1
    exam_ids = {a.exam_id for a in attempts if a.exam_id}
    exam_map = {}
    if exam_ids:
        for r in db.query(ExamRecord).filter(ExamRecord.id.in_(exam_ids)).all():
            exam_map[r.id] = r
    return [
        {
            "id": a.id,
            "exam_id": a.exam_id,
            "score": a.score,
            "total": a.total,
            "correct": a.correct,
            "wrong": a.wrong,
            "duration_sec": a.duration_sec,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "exam_title": exam_map[a.exam_id].title if a.exam_id in exam_map else "",
            "subject": exam_map[a.exam_id].subject if a.exam_id in exam_map else "",
        }
        for a in attempts
    ]


@router.get("/attempts/{attempt_id}", summary="单次做题详情")
def get_attempt_detail(attempt_id: int, db: Session = Depends(get_db)):
    attempt = db.query(ExamAttempt).get(attempt_id)
    if not attempt:
        raise HTTPException(404, "记录不存在")
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    detail = []
    for aa in answers:
        q = db.query(Question).get(aa.question_id)
        detail.append({
            "question_id": aa.question_id,
            "user_answer": aa.user_answer,
            "is_correct": aa.is_correct,
            "question": q.question if q else "",
            "correct_answer": q.answer if q else "",
            "type_name": q.type_name if q else "",
        })
    return {
        "id": attempt.id,
        "exam_id": attempt.exam_id,
        "user_id": attempt.user_id,
        "score": attempt.score,
        "total": attempt.total,
        "correct": attempt.correct,
        "wrong": attempt.wrong,
        "created_at": attempt.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "answers": detail,
    }


__all__ = ["submit_answers", "list_attempts", "get_attempt_detail"]
