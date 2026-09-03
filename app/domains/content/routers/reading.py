"""阅读理解专项路由

- GET  /api/reading/passages  按学科+年级抽篇（刷题中心「阅读专项」入口）
- POST /api/reading/submit    交卷判分（客观即时判 + 主观 AI 判分）
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.reading_service import get_passages, submit_reading_quiz

router = APIRouter()


class ReadingAnswer(BaseModel):
    qid: int
    user_answer: str = ""


class ReadingSubmitRequest(BaseModel):
    user_id: str
    passage_id: int
    answers: List[ReadingAnswer]


@router.get("/passages", summary="阅读理解抽篇（按学科+年级）")
def reading_passages(
    subject: str = Query("英语", description="学科：语文/英语"),
    grade: int = Query(7, description="年级"),
    limit: int = Query(5, ge=1, le=20, description="抽取篇数"),
    db: Session = Depends(get_db),
):
    """阅读理解抽篇（刷题中心「阅读专项」入口），按学科+年级随机抽若干篇。

    参数（Query）：subject（语文/英语，默认英语）、grade、limit（1-20，默认 5）。
    返回：{subject, grade, passages[篇列表]}；subject 非法返回 400。
    副作用：无（只读）。无需家长密码。
    """
    if subject not in ("语文", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/英语")
    passages = get_passages(db, subject, grade, limit)
    return {"subject": subject, "grade": grade, "passages": passages}


@router.post("/submit", summary="阅读理解交卷判分（客观即时判 + 主观 AI 判分）")
def reading_submit(req: ReadingSubmitRequest):
    """阅读理解交卷判分：客观题即时判分，主观题走 AI 判分。

    参数（Body）：user_id、passage_id、answers[{qid, user_answer}]。
    返回：判分结果（由 reading_service.submit_reading_quiz 决定结构，含得分/明细）。
    副作用：可能写答题/判分记录；业务异常（如篇不存在）返回 400。
    无需家长密码。服务内部短会话，等待 AI 期间不占连接池。
    """
    try:
        result = submit_reading_quiz(
            req.user_id, req.passage_id, [a.model_dump() for a in req.answers],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result
