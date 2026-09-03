"""采集题库刷题（paper_questions）相关端点"""
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import router
from .common import _check_answer
from app.database import get_db
from app.models.paper import PaperQuestion
from app.schemas.exam import (
    CollectionPracticeQuestionOut, CollectionSubmitRequest,
)
from app.domains.assessment.services.collection_practice import (
    random_paper_questions, get_paper_questions_by_ids, collection_stats,
    mixed_practice,
)


def _pq_to_dict(q: PaperQuestion, include_answer: bool = True) -> dict:
    """将单道采集题序列化为刷题接口输出。"""
    import json as _json
    options = []
    if q.options:
        try:
            options = _json.loads(q.options)
        except Exception:
            options = []
    return {
        "id": q.id,
        "paper_id": q.paper_id,
        "seq": q.seq,
        "grade": q.grade or "",
        "subject": q.subject or "",
        "qtype": q.qtype or "",
        "section": q.section or "",
        "question_html": q.question_html or "",
        "image_base64": q.image_base64 or "",
        "options": list(options) if isinstance(options, list) else [],
        "correct_answer": (q.correct_answer or "") if include_answer else "",
    }


@router.get("/collection/practice", response_model=List[CollectionPracticeQuestionOut],
            summary="采集题库抽题 / 组合刷题（题库+AI自适应）")
def collection_practice(
    grade: Optional[str] = Query(None, description="年级，如 一年级 / 初三 / 中考"),
    subject: Optional[str] = Query(None, description="学科，如 数学 / 语文"),
    qtype: Optional[str] = Query(None, description="题型：choice / fill_blank / qa"),
    limit: int = Query(10, ge=1, le=50, description="抽题数量"),
    mode: str = Query("bank", description="bank=仅题库 / mixed=题库+AI自适应补足 / ai=仅AI生成"),
    include_answer: bool = Query(True, description="是否附带参考答案（练习时建议先 False）"),
    db: Session = Depends(get_db),
):
    """从采集题库（或组合 AI 生成）抽题，供刷题系统使用。

    - mode=bank（默认）：仅从 paper_questions 随机抽题（原行为）。
    - mode=mixed：优先题库，题库不足该学科/题型时用 AI 实时生成补足（自适应）。
    - mode=ai：仅用 AI 生成（适合题库空或特定薄弱点强化）。
    - AI 题以 source="ai"、id<=0 标记，提交判分时用携带答案（见 /collection/submit）。
    """
    if mode == "bank":
        qs = random_paper_questions(db, grade=grade, subject=subject, qtype=qtype, limit=limit)
        return [_pq_to_dict(q, include_answer) for q in qs]
    items = mixed_practice(db, grade=grade, subject=subject, qtype=qtype,
                           limit=limit, ai_fill=(mode != "ai"))
    if not include_answer:
        for it in items:
            it["correct_answer"] = ""
    return items


@router.get("/collection/stats", summary="采集题库规模统计")
def collection_practice_stats(db: Session = Depends(get_db)):
    """返回采集题库总量与按学科/年级的分布，便于前端展示与最终验证。"""
    return collection_stats(db)


@router.post("/collection/submit", summary="采集题库刷题提交判分")
def collection_submit(req: CollectionSubmitRequest, db: Session = Depends(get_db)):
    """对采集题库所做题目判分，返回每题对错与总分。

    与原有 submit-answers 解耦：本题库 id 空间为 paper_questions，
    不改写原有 questions 错题本（ID 空间隔离）；如需错题沉淀可后续单独扩展。
    """
    if not req.answers:
        raise HTTPException(400, "answers 不能为空")
    ids = [a.get("question_id") for a in req.answers if a.get("question_id")]
    qmap = get_paper_questions_by_ids(db, ids) if ids else {}
    results = []
    correct_count = 0
    for a in req.answers:
        qid = a.get("question_id")
        user_ans = str(a.get("user_answer", "")).strip()
        q = qmap.get(qid)
        if q:
            ok = _check_answer(user_ans, q.correct_answer or "", q.options)
            std = q.correct_answer or ""
        elif qid is not None and str(qid).lstrip("-").isdigit() and int(qid) <= 0:
            # AI 生成题（id<=0）：用前端携带的标准答案判分，不查库
            std = a.get("correct_answer") or ""
            ok = _check_answer(user_ans, std, "")
        else:
            results.append({"question_id": qid, "correct": False, "error": "题目不存在"})
            continue
        if ok:
            correct_count += 1
        results.append({
            "question_id": qid,
            "correct": ok,
            "correct_answer": std,
        })
    total = len(req.answers)
    return {
        "user_id": req.user_id,
        "total": total,
        "correct": correct_count,
        "score": round(correct_count * 100 / total, 1) if total else 0,
        "results": results,
    }


__all__ = ["_pq_to_dict", "collection_practice", "collection_practice_stats", "collection_submit"]
