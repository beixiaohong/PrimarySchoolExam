"""错题管理、列表、专项练习、统计与未答题作答端点"""
import json
import random
from collections import defaultdict
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import router
from .common import _check_answer
from app.database import get_db
from app.models.exam import WrongRecord, Question, AttemptAnswer, ExamAttempt, ExamRecord
from app.schemas.exam import (
    MarkWrongRequest, WrongRecordOut, WrongPracticeRequest,
)


@router.post("/{exam_id}/mark-wrong", summary="标记错题")
def mark_wrong(exam_id: int, req: MarkWrongRequest, db: Session = Depends(get_db)):
    """
    将指定试卷中的题目标记为某用户的错题。
    定位方式：question_ids（数据库ID）或 seqs（试卷内序号），二选一。
    重复标记不会创建重复记录。
    """
    questions = _locate_questions(db, exam_id, req.question_ids, req.seqs)
    now = datetime.now()
    marked = 0
    for q in questions:
        existing = db.query(WrongRecord).filter(
            WrongRecord.user_id == req.user_id,
            WrongRecord.question_id == q.id,
        ).first()
        if existing:
            # 已存在则更新（可能之前标记已掌握，现在重新标错）
            existing.is_mastered = False
            existing.mastered_at = None
            existing.correct_streak = 0  # 重新标错：连击清零，闭环重新开始
            existing.wrong_at = now
        else:
            db.add(WrongRecord(
                user_id=req.user_id,
                question_id=q.id,
                wrong_at=now,
            ))
        marked += 1
    db.commit()
    return {"message": f"已标记 {marked} 道错题", "exam_id": exam_id, "user_id": req.user_id, "marked_count": marked}


@router.post("/{exam_id}/unmark-wrong", summary="取消错题标记")
def unmark_wrong(exam_id: int, req: MarkWrongRequest, db: Session = Depends(get_db)):
    """从用户的错题本中移除指定题目"""
    questions = _locate_questions(db, exam_id, req.question_ids, req.seqs)
    removed = 0
    for q in questions:
        wr = db.query(WrongRecord).filter(
            WrongRecord.user_id == req.user_id,
            WrongRecord.question_id == q.id,
        ).first()
        if wr:
            db.delete(wr)
            removed += 1
    db.commit()
    return {"message": f"已移除 {removed} 道错题", "removed_count": removed}


@router.post("/{exam_id}/master", summary="标记已掌握")
def mark_mastered(exam_id: int, req: MarkWrongRequest, db: Session = Depends(get_db)):
    """
    将错题标记为"已掌握"。
    已掌握的题目不再出现在错题练习中，但保留记录。
    """
    questions = _locate_questions(db, exam_id, req.question_ids, req.seqs)
    now = datetime.now()
    mastered = 0
    for q in questions:
        wr = db.query(WrongRecord).filter(
            WrongRecord.user_id == req.user_id,
            WrongRecord.question_id == q.id,
        ).first()
        if wr:
            wr.is_mastered = True
            wr.mastered_at = now
            wr.next_review_date = None   # 掌握出队（明日复习队列）
            mastered += 1
    db.commit()
    return {"message": f"已标记 {mastered} 题为已掌握", "mastered_count": mastered}


@router.get("/wrong/list", response_model=List[WrongRecordOut], summary="查看用户错题列表")
def list_wrong_questions(
    user_id: str = Query(..., description="用户标识"),
    subject: str = Query(None, description="学科筛选：数学/英语"),
    type_code: str = Query(None, description="题型代码筛选"),
    include_mastered: bool = Query(False, description="是否包含已掌握的题"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """分页查询指定用户的错题本列表，按标记错题时间倒序。

    参数：user_id 用户标识（必填）；subject 可选学科筛选；
    type_code 可选题型代码筛选；include_mastered 是否包含已掌握题；
    page/page_size 分页。返回错题明细（展开题目信息 + 用户最近一次实际作答）。
    """
    q = db.query(WrongRecord).filter(WrongRecord.user_id == user_id)
    if not include_mastered:
        q = q.filter(WrongRecord.is_mastered == False)

    # 联查题目信息
    q = q.join(Question)
    if subject:
        q = q.filter(Question.subject == subject)
    if type_code:
        q = q.filter(Question.type_code == type_code)

    records = q.order_by(WrongRecord.wrong_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return [_wrong_record_to_out(wr, db) for wr in records]


@router.post("/wrong/practice", summary="错题专项练习（生成Word下载）")
def wrong_practice(req: WrongPracticeRequest, db: Session = Depends(get_db)):
    """
    从用户的错题本中抽取题目，生成专项练习Word文档。
    - 已标记"已掌握"的题目不会被抽取
    - 支持按学科、题型筛选（数学/英语均可）
    - 每次练习后自动累加 practice_count
    """
    from app.domains.assessment.services.docx_service import build_wrong_practice_docx

    q = db.query(WrongRecord).filter(
        WrongRecord.user_id == req.user_id,
        or_(WrongRecord.is_mastered.is_(None), WrongRecord.is_mastered != True),
    ).join(Question)

    if req.subject:
        q = q.filter(Question.subject == req.subject)
    if req.type_code:
        q = q.filter(Question.type_code == req.type_code)

    all_wrong = q.order_by(WrongRecord.wrong_at.desc()).all()
    if not all_wrong:
        raise HTTPException(404, "暂无错题记录（或全部已掌握）")

    selected = random.sample(all_wrong, min(req.count, len(all_wrong)))
    selected.sort(key=lambda wr: (wr.question.subject, wr.question.type_code, wr.question.seq))

    # 累加练习次数
    for wr in selected:
        wr.practice_count += 1
    db.commit()

    # 传入 Question 对象列表给 docx 生成
    question_list = [wr.question for wr in selected]
    filepath = build_wrong_practice_docx(question_list, include_answer=req.include_answer)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="错题专项练习.docx",
    )


class WrongPracticeQuizRequest(BaseModel):
    """错题在线练习抽题（JSON，供前端直接答题）"""
    user_id: str = Field(..., max_length=64, description="用户标识")
    subject: Optional[str] = Field(None, description="学科筛选：数学/英语，不填则混合")
    count: int = Field(5, ge=1, le=50, description="抽题组数（每组 3 道同类型题，默认 5 组）")


def _parse_options_json(options_json: Optional[str]) -> list:
    """解析选项 JSON 字符串，失败返回空列表"""
    if not options_json:
        return []
    try:
        data = json.loads(options_json)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


@router.post("/wrong/practice-quiz", summary="错题修正练习抽题（每道错题配 3 道同类型题）")
def wrong_practice_quiz(req: WrongPracticeQuizRequest, db: Session = Depends(get_db)):
    """从用户未掌握的错题中随机抽 count 道错题（默认 5），每道错题配 3 道同类型新题。

    - 「修正」规则：同类型 = type_code 相同（无 type_code 时退化为 category 相同）
      且同学科、非原题；同类型题不足 3 道时按实际数量返回（防刷：不用原题补齐，
      避免背答案）
    - 返回分组结构，前端整组答题，整组全对才提交修正
      （/api/study/practice-submit 按 record_id 分组判定，全对直接掌握）
    """
    q = db.query(WrongRecord).filter(
        WrongRecord.user_id == req.user_id,
        or_(WrongRecord.is_mastered.is_(None), WrongRecord.is_mastered != True),
        or_(WrongRecord.is_unanswered.is_(None), WrongRecord.is_unanswered != True),
    ).join(Question)

    if req.subject:
        q = q.filter(Question.subject == req.subject)

    all_wrong = q.order_by(WrongRecord.wrong_at.desc()).all()
    if not all_wrong:
        raise HTTPException(404, "暂无错题可练习（或全部已掌握）")

    selected = random.sample(all_wrong, min(req.count, len(all_wrong)))
    groups = []
    for wr in selected:
        qs = wr.question
        # 同类型候选池：同学科 + type_code 相同（无 type_code 退化为 category）
        pool = db.query(Question).filter(
            Question.subject == qs.subject,
            Question.id != qs.id,
        )
        if qs.type_code:
            pool = pool.filter(Question.type_code == qs.type_code)
        elif qs.category:
            pool = pool.filter(Question.category == qs.category)
        candidates = pool.order_by(Question.seq).all()
        picks = random.sample(candidates, min(3, len(candidates))) if candidates else []
        # 防刷：同类型题不足 3 道时按实际数量返回，不用原题补齐（避免直接背答案）

        group_questions = [{
            "qid": qu.id,
            "kind": "exam",
            "record_id": wr.id,
            "question": qu.question,
            "options": _parse_options_json(qu.options_json),
            # 防刷：不下发正确答案，逐题判分走 /api/study/check-answer
            "explanation": "",
            "type_name": qu.type_name or "",
            "subject": qu.subject,
            "exam_id": qu.exam_id,
        } for qu in picks]
        groups.append({
            "record_id": wr.id,
            "qid": wr.question_id,
            "type_name": qs.type_name or "",
            "subject": qs.subject,
            "questions": group_questions,
        })

    return {"count": len(groups), "groups": groups}


@router.get("/wrong/stats", summary="错题分析（按题型统计）")
def wrong_stats(
    user_id: str = Query(..., description="用户标识"),
    subject: str = Query(None, description="学科筛选"),
    db: Session = Depends(get_db),
):
    """
    错题分析：按题型分组统计错题数量、已掌握数量、练习次数。
    """
    q = db.query(WrongRecord).filter(WrongRecord.user_id == user_id).join(Question)
    if subject:
        q = q.filter(Question.subject == subject)

    records = q.all()
    if not records:
        return {"total_wrong": 0, "total_mastered": 0, "by_type": []}

    # 按 type_code 分组
    groups = defaultdict(lambda: {"wrong": 0, "mastered": 0, "practice_total": 0, "type_name": "", "subject": ""})
    for wr in records:
        qc = wr.question.type_code or "unknown"
        g = groups[qc]
        g["type_name"] = wr.question.type_name or qc
        g["subject"] = wr.question.subject
        g["practice_total"] += wr.practice_count
        if wr.is_mastered:
            g["mastered"] += 1
        else:
            g["wrong"] += 1

    by_type = []
    for code, g in sorted(groups.items(), key=lambda x: -x[1]["wrong"]):
        by_type.append({
            "type_code": code,
            "type_name": g["type_name"],
            "subject": g["subject"],
            "wrong_count": g["wrong"],
            "mastered_count": g["mastered"],
            "practice_total": g["practice_total"],
        })

    total_wrong = sum(g["wrong"] for g in groups.values())
    total_mastered = sum(g["mastered"] for g in groups.values())
    return {"total_wrong": total_wrong, "total_mastered": total_mastered, "by_type": by_type}


@router.post("/wrong/answer-unanswered", summary="未答题作答（错题本中先做再判对错）")
def answer_unanswered(req, db: Session = Depends(get_db)):
    """错题本中「未答」的题：用户作答后判对错。
    - 答对 → 直接标记已掌握（相当于用户会了）
    - 答错 → 标记为「答错」（is_unanswered=False），保留在错题本
    """
    rec = db.query(WrongRecord).filter(
        WrongRecord.id == req.record_id,
        WrongRecord.user_id == req.user_id,
    ).first()
    if not rec:
        raise HTTPException(404, "错题记录不存在")

    q = rec.question
    is_correct = _check_answer(req.user_answer, q.answer.strip(), q.options_json)

    if is_correct:
        rec.is_mastered = True
        rec.is_unanswered = False
        rec.mastered_at = datetime.now()
        rec.next_review_date = None
        rec.correct_streak = 3
        db.commit()
        # 答对发金币
        try:
            from app.domains.engagement.contracts import PetService
            PetService.grant_coins(db, req.user_id, 3, "未答题答对")
        except Exception:
            pass
        return {"correct": True, "mastered": True, "message": "答对了！已标记为已掌握"}
    else:
        rec.is_unanswered = False
        rec.wrong_at = datetime.now()
        db.commit()
        return {
            "correct": False, "mastered": False,
            "correct_answer": q.answer,
            "message": "答错了，已标记为答错，继续加油！",
        }


class AnswerUnansweredRequest(BaseModel):
    """未答错题作答请求体：用户补全错题本中「未作答」题目的答案。"""
    user_id: str
    record_id: int
    user_answer: str


@router.post("/wrong/batch-master", summary="批量标记错题已掌握")
def batch_master(req: dict, db: Session = Depends(get_db)):
    """
    批量将错题标记为已掌握（不需要 exam_id）。
    请求体: { "user_id": "xxx", "question_ids": [1, 2, 3] }
    """
    user_id = req.get("user_id", "")
    question_ids = req.get("question_ids", [])
    if not isinstance(question_ids, list) or not all(isinstance(x, int) for x in question_ids):
        raise HTTPException(400, "question_ids 必须是整数数组")
    if not user_id or not question_ids:
        raise HTTPException(400, "缺少 user_id 或 question_ids")

    now = datetime.now()
    mastered = 0
    for qid in question_ids:
        wr = db.query(WrongRecord).filter(
            WrongRecord.user_id == user_id,
            WrongRecord.question_id == qid,
        ).first()
        if wr and not wr.is_mastered:
            wr.is_mastered = True
            wr.mastered_at = now
            wr.next_review_date = None   # 掌握出队（明日复习队列）
            mastered += 1
    db.commit()
    return {"message": f"已标记 {mastered} 题为已掌握", "mastered_count": mastered}


def _locate_questions(db: Session, exam_id: int, question_ids: list = None, seqs: list = None) -> list:
    """根据 question_ids 或 seqs 定位题目"""
    record = db.get(ExamRecord, exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")

    if question_ids:
        questions = db.query(Question).filter(
            Question.id.in_(question_ids),
            Question.exam_id == exam_id,
        ).all()
    elif seqs:
        questions = db.query(Question).filter(
            Question.exam_id == exam_id,
            Question.seq.in_(seqs),
        ).all()
    else:
        raise HTTPException(400, "请提供 question_ids 或 seqs")

    if not questions:
        raise HTTPException(404, "未找到匹配的题目")
    return questions


def _wrong_record_to_out(wr: WrongRecord, db: Session = None) -> WrongRecordOut:
    """WrongRecord ORM → WrongRecordOut（展开题目信息 + 用户实际作答）"""
    q = wr.question

    # 查询用户最近一次作答内容（通过 ExamAttempt + AttemptAnswer 联查）
    user_answer = ""
    if db is not None:
        latest_aa = (
            db.query(AttemptAnswer)
            .join(ExamAttempt, AttemptAnswer.attempt_id == ExamAttempt.id)
            .filter(
                ExamAttempt.user_id == wr.user_id,
                AttemptAnswer.question_id == wr.question_id,
            )
            .order_by(ExamAttempt.id.desc())
            .first()
        )
        if latest_aa:
            user_answer = (latest_aa.user_answer or "").strip()

    # 以实际作答内容为准判断是否未答（兜底修正）
    is_unanswered = wr.is_unanswered or False
    if user_answer:
        is_unanswered = False

    return WrongRecordOut(
        id=wr.id,
        user_id=wr.user_id,
        question_id=wr.question_id,
        is_mastered=wr.is_mastered,
        is_unanswered=is_unanswered,
        practice_count=wr.practice_count,
        cause=wr.cause or "",
        wrong_at=wr.wrong_at.strftime("%Y-%m-%d %H:%M:%S") if wr.wrong_at else None,
        mastered_at=wr.mastered_at.strftime("%Y-%m-%d %H:%M:%S") if wr.mastered_at else None,
        user_answer=user_answer,
        exam_id=q.exam_id,
        seq=q.seq,
        subject=q.subject,
        category=q.category,
        type_code=q.type_code,
        type_name=q.type_name,
        question=q.question,
        answer=q.answer,
        options_json=q.options_json,
        difficulty=q.difficulty,
    )


__all__ = [
    "mark_wrong", "unmark_wrong", "mark_mastered", "list_wrong_questions",
    "wrong_practice", "wrong_practice_quiz", "WrongPracticeQuizRequest",
    "_parse_options_json", "wrong_stats", "answer_unanswered",
    "AnswerUnansweredRequest", "batch_master", "_locate_questions",
    "_wrong_record_to_out",
]
