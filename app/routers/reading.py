"""阅读理解专项路由

- GET  /api/reading/passages  按学科+年级抽篇（刷题中心「阅读专项」入口）
- POST /api/reading/submit    交卷判分（客观即时判 + 主观 AI 判分）
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.reading_service import get_passages, submit_reading_quiz

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
    if subject not in ("语文", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/英语")
    passages = get_passages(db, subject, grade, limit)
    return {"subject": subject, "grade": grade, "passages": passages}


@router.post("/submit", summary="阅读理解交卷判分（客观即时判 + 主观 AI 判分）")
def reading_submit(req: ReadingSubmitRequest, db: Session = Depends(get_db)):
    try:
        result = submit_reading_quiz(
            db, req.user_id, req.passage_id, [a.model_dump() for a in req.answers],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result
