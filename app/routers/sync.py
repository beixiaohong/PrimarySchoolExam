"""同步学路由：单元导航 / 要点 / 同步练习 / 单元小测

信息架构：学科 tab → 当前年级+学期的单元卡片列表（含状态/小测最佳/练习数）
→ 单元详情（要点 + 同步练习 + 单元小测）。单元小测判分落库 sync_quiz_log，
并联动每日 *_sync 任务（D3 决议，无需家长确认）。
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.sync_service import (
    build_overview, build_unit_points, build_unit_practice,
    generate_unit_quiz, judge_unit_quiz,
)

router = APIRouter()


class UnitQuizAnswer(BaseModel):
    qid: int
    user_answer: str = ""


class UnitQuizRequest(BaseModel):
    user_id: str
    subject: str
    grade: int = 6
    unit: str
    token: str
    answers: List[UnitQuizAnswer]


@router.get("/overview", summary="同步学单元总览（含状态/小测最佳/练习数）")
def sync_overview(
    user_id: str = Query(..., description="用户名"),
    subject: str = Query("英语", description="学科：语文/数学/英语"),
    grade: int = Query(6, description="年级"),
    include_next: bool = Query(False, description="是否包含下学期预习单元"),
    db: Session = Depends(get_db),
):
    if subject not in ("语文", "数学", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/数学/英语")
    units = build_overview(db, user_id, subject, grade, include_next)
    return {"subject": subject, "grade": grade, "units": units}


@router.get("/unit-points", summary="单元要点（词表/篇目/题型清单）")
def unit_points(
    subject: str = Query(..., description="学科"),
    grade: int = Query(6, description="年级"),
    unit: str = Query(..., description="单元标识"),
    db: Session = Depends(get_db),
):
    if subject not in ("语文", "数学", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/数学/英语")
    return build_unit_points(db, subject, grade, unit)


@router.get("/unit-practice", summary="单元同步练习（随做随判，含答案）")
def unit_practice(
    subject: str = Query(..., description="学科"),
    grade: int = Query(6, description="年级"),
    unit: str = Query(..., description="单元标识"),
    count: int = Query(10, ge=1, le=30, description="题数"),
    db: Session = Depends(get_db),
):
    if subject not in ("语文", "数学", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/数学/英语")
    return build_unit_practice(db, subject, grade, unit, count)


@router.get("/unit-quiz/generate", summary="生成单元小测题目（不含答案，返回签名 token）")
def unit_quiz_generate(
    subject: str = Query(..., description="学科"),
    grade: int = Query(6, description="年级"),
    unit: str = Query(..., description="单元标识"),
    count: int = Query(10, ge=1, le=30, description="题数"),
    db: Session = Depends(get_db),
):
    if subject not in ("语文", "数学", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/数学/英语")
    return generate_unit_quiz(db, subject, grade, unit, count)


@router.post("/unit-quiz", summary="单元小测（整卷判分，成绩落库，错题入错题本，联动 *_sync 任务）")
def unit_quiz(req: UnitQuizRequest, db: Session = Depends(get_db)):
    if req.subject not in ("语文", "数学", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/数学/英语")
    try:
        result = judge_unit_quiz(
            db, req.user_id, req.subject, req.grade, req.unit,
            req.token, [a.model_dump() for a in req.answers],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result
