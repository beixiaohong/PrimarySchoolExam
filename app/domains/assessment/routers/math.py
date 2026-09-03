"""数学题目 API 路由

提供题型（大类/题型）的增删改查，以及按年级、难度、题型配置生成数学题（含导出 Word 并入库）。
所有接口只读或写本地题库，无需家长密码。
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import (
    ProblemTypeCreate, ProblemTypeOut, CategoryOut,
    MathGenRequest, MathGenResponse,
)
from ..services.math_generator import generate_math_problems

router = APIRouter()


# ─── 题型管理 ───────────────────────────────────────────────

@router.get("/categories", response_model=List[CategoryOut], summary="获取所有题目大类及题型")
def list_categories(db: Session = Depends(get_db)):
    """获取所有题目大类及下属题型列表。

    参数（Query）：无。
    返回：处于启用状态（is_active=True）的 ProblemCategory 列表。
    副作用：无（只读）。无需家长密码。
    """
    return db.query(ProblemCategory).filter(ProblemCategory.is_active == True).all()


@router.get("/types", response_model=List[ProblemTypeOut], summary="查询题型列表")
def list_types(
    category_id: Optional[int] = Query(None),
    grade: Optional[int] = Query(None, ge=1, le=6),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    """查询题型列表，支持按大类、年级、是否启用过滤。

    参数（Query）：
      - category_id：按大类过滤（可选）。
      - grade：1-6 年级，命中 grade_min<=grade<=grade_max 的题型（可选）。
      - active_only：是否只返回启用题型（默认 True）。
    返回：ProblemTypeOut 列表。
    副作用：无（只读）。无需家长密码。
    """
    q = db.query(ProblemType)
    if category_id:
        q = q.filter(ProblemType.category_id == category_id)
    if grade:
        q = q.filter(ProblemType.grade_min <= grade, ProblemType.grade_max >= grade)
    if active_only:
        q = q.filter(ProblemType.is_active == True)
    return q.all()


@router.post("/types", response_model=ProblemTypeOut, summary="新增题型")
def create_type(data: ProblemTypeCreate, db: Session = Depends(get_db)):
    """新增题型。

    参数（Body）：题型字段（code 为唯一业务编码）。
    返回：新建的 ProblemTypeOut。
    副作用：写入 ProblemType 表；若 code 已存在返回 409。
    无需家长密码。
    """
    existing = db.query(ProblemType).filter(ProblemType.code == data.code).first()
    if existing:
        raise HTTPException(409, f"题型编码 '{data.code}' 已存在")
    pt = ProblemType(**data.model_dump())
    db.add(pt)
    db.commit()
    db.refresh(pt)
    return pt


@router.put("/types/{type_id}", response_model=ProblemTypeOut, summary="更新题型")
def update_type(type_id: int, data: ProblemTypeCreate, db: Session = Depends(get_db)):
    """更新题型（全量覆盖可写字段）。

    参数（Path）：type_id 题型主键。
    参数（Body）：题型字段。
    返回：更新后的 ProblemTypeOut；type_id 不存在返回 404。
    副作用：更新 ProblemType 表。无需家长密码。
    """
    pt = db.get(ProblemType, type_id)
    if not pt:
        raise HTTPException(404, "题型不存在")
    for k, v in data.model_dump().items():
        setattr(pt, k, v)
    db.commit()
    db.refresh(pt)
    return pt


@router.delete("/types/{type_id}", summary="删除题型")
def delete_type(type_id: int, db: Session = Depends(get_db)):
    """删除题型。

    参数（Path）：type_id 题型主键。
    返回：{"message": "已删除"}；type_id 不存在返回 404。
    副作用：删除 ProblemType 表记录。无需家长密码。
    """
    pt = db.get(ProblemType, type_id)
    if not pt:
        raise HTTPException(404, "题型不存在")
    db.delete(pt)
    db.commit()
    return {"message": "已删除"}


# ─── 题目生成 ───────────────────────────────────────────────

@router.post("/generate", response_model=MathGenResponse, summary="生成数学题")
def generate(req: MathGenRequest, db: Session = Depends(get_db)):
    """
    根据年级、难度、题型配置生成数学题目。
    难度说明：基础(1-2步) / 提高(2-3步) / 拔高(3-4步) / 综合(混合)
    """
    problems = generate_math_problems(
        grade=req.grade,
        difficulty=req.difficulty,
        categories=req.categories,
        problem_types=req.problem_types,
        count=req.count,
        include_answer=req.include_answer,
        db=db,
    )
    return MathGenResponse(
        total=len(problems),
        difficulty=req.difficulty,
        grade=req.grade,
        problems=problems,
    )


@router.post("/generate/docx", summary="生成数学题并导出Word（题目自动入库）")
def generate_docx(req: MathGenRequest, db: Session = Depends(get_db)):
    """生成数学题并返回Word文档下载，同时将所有题目保存到数据库"""
    import json
    from ..services.docx_service import build_math_docx
    from app.models.exam import ExamRecord, Question

    problems = generate_math_problems(
        grade=req.grade,
        difficulty=req.difficulty,
        categories=req.categories,
        problem_types=req.problem_types,
        count=req.count,
        include_answer=True,
        db=db,
    )
    filepath = build_math_docx(problems, req.grade, req.difficulty)

    # 试卷记录入库（公共，不绑定用户）
    title = f"{req.grade}年级数学练习_{req.difficulty}"
    record = ExamRecord(
        subject="数学",
        title=title,
        grade=req.grade,
        difficulty=req.difficulty,
        config_json=json.dumps(req.model_dump(), ensure_ascii=False),
        file_path=filepath,
        question_count=len(problems),
    )
    db.add(record)
    db.flush()

    # 逐题入库
    for i, p in enumerate(problems, 1):
        db.add(Question(
            exam_id=record.id,
            seq=i,
            subject="数学",
            category=p.category,
            type_code=p.type_code,
            type_name=p.type_name,
            question=p.question,
            answer=p.answer,
            exact_answer=getattr(p, "exact_answer", "") or "",
            difficulty=p.difficulty,
        ))
    db.commit()

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{title}.docx",
    )
