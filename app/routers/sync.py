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
    generate_unit_quiz, judge_unit_quiz, MIDDLE_SUBJECTS,
)

# 同步学支持的全部学科：小学语数英 + 初中六科
VALID_SUBJECTS = ["语文", "数学", "英语"] + MIDDLE_SUBJECTS

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
    """同步学单元总览：学科+年级下的单元卡片列表（含完成状态/小测最佳分/练习数）。

    参数（Query）：user_id、subject（语文/数学/英语）、grade、include_next（含下学期预习单元）。
    返回：{subject, grade, units[]}；subject 非法返回 400。
    副作用：无（只读）。无需家长密码。
    """
    if subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"subject 仅支持 {('/'.join(VALID_SUBJECTS))}")
    units = build_overview(db, user_id, subject, grade, include_next)
    return {"subject": subject, "grade": grade, "units": units}


@router.get("/unit-points", summary="单元要点（词表/篇目/题型清单）")
def unit_points(
    subject: str = Query(..., description="学科"),
    grade: int = Query(6, description="年级"),
    unit: str = Query(..., description="单元标识"),
    db: Session = Depends(get_db),
):
    """单元要点：返回该单元的词表/篇目/题型清单。

    参数（Query）：subject、grade、unit。
    返回：单元要点结构（由 build_unit_points 决定）。
    副作用：无（只读）。无需家长密码。
    """
    if subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"subject 仅支持 {('/'.join(VALID_SUBJECTS))}")
    return build_unit_points(db, subject, grade, unit)


@router.get("/unit-practice", summary="单元同步练习（随做随判，含答案）")
def unit_practice(
    subject: str = Query(..., description="学科"),
    grade: int = Query(6, description="年级"),
    unit: str = Query(..., description="单元标识"),
    count: int = Query(10, ge=1, le=30, description="题数"),
    db: Session = Depends(get_db),
):
    """单元同步练习：随做随判，直接返回题目与答案。

    参数（Query）：subject、grade、unit、count（1-30）。
    返回：练习题目结构（含答案，由 build_unit_practice 决定）。
    副作用：无（只读）。无需家长密码。
    """
    if subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"subject 仅支持 {('/'.join(VALID_SUBJECTS))}")
    return build_unit_practice(db, subject, grade, unit, count)


@router.get("/unit-quiz/generate", summary="生成单元小测题目（不含答案，返回签名 token）")
def unit_quiz_generate(
    subject: str = Query(..., description="学科"),
    grade: int = Query(6, description="年级"),
    unit: str = Query(..., description="单元标识"),
    count: int = Query(10, ge=1, le=30, description="题数"),
    db: Session = Depends(get_db),
):
    """生成单元小测题目（不含答案，下发签名 token 用于交卷校验防篡改）。

    参数（Query）：subject、grade、unit、count（1-30）。
    返回：{questions(无答案), token}；subject 非法返回 400。
    副作用：无（只读）。无需家长密码。
    """
    if subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"subject 仅支持 {('/'.join(VALID_SUBJECTS))}")
    return generate_unit_quiz(db, subject, grade, unit, count)


@router.post("/unit-quiz", summary="单元小测（整卷判分，成绩落库，错题入错题本，联动 *_sync 任务）")
def unit_quiz(req: UnitQuizRequest, db: Session = Depends(get_db)):
    """单元小测交卷：整卷判分，成绩落库 sync_quiz_log，错题入错题本，联动 *_sync 每日任务。

    参数（Body）：user_id、subject、grade、unit、token（生成时返回的签名）、answers[{qid, user_answer}]。
    返回：判分结果（由 judge_unit_quiz 决定，含得分/明细/错题）。
    副作用：写 sync_quiz_log、可能写错题本、联动每日 sync 任务；subject 非法/校验失败返回 400。
    无需家长密码。
    """
    if req.subject not in VALID_SUBJECTS:
        raise HTTPException(400, f"subject 仅支持 {('/'.join(VALID_SUBJECTS))}")
    try:
        result = judge_unit_quiz(
            db, req.user_id, req.subject, req.grade, req.unit,
            req.token, [a.model_dump() for a in req.answers],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result
