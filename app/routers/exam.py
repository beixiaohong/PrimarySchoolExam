"""试卷生成 API 路由"""
import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.exam import ExamRecord
from ..schemas.exam import ExamCreateRequest, ExamOut

router = APIRouter()


@router.post("/generate", summary="生成试卷（返回下载）")
def generate_exam(req: ExamCreateRequest, db: Session = Depends(get_db)):
    """
    生成完整试卷并返回Word文档下载。
    数学试卷：计算题+应用题，按难度梯度分布。
    英语试卷：单词听写+选择+翻译+词组句。
    """
    if req.subject == "数学":
        filepath = _generate_math_exam(req, db)
    elif req.subject == "英语":
        filepath = _generate_english_exam(req, db)
    else:
        raise HTTPException(400, "学科仅支持：数学/英语")

    title = req.title or f"{req.grade}年级{req.subject}试卷_{req.difficulty}"
    record = ExamRecord(
        subject=req.subject,
        title=title,
        grade=req.grade,
        difficulty=req.difficulty,
        config_json=json.dumps(req.model_dump(), ensure_ascii=False),
        file_path=filepath,
        question_count=req.math_count if req.subject == "数学" else req.english_word_count,
    )
    db.add(record)
    db.commit()

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{title}.docx",
    )


@router.get("/records", response_model=List[ExamOut], summary="试卷生成记录")
def list_records(
    subject: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(ExamRecord)
    if subject:
        q = q.filter(ExamRecord.subject == subject)
    records = q.order_by(ExamRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = []
    for r in records:
        result.append(ExamOut(
            id=r.id, subject=r.subject, title=r.title,
            grade=r.grade, difficulty=r.difficulty,
            question_count=r.question_count, file_path=r.file_path,
            created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    return result


@router.get("/download/{record_id}", summary="下载已生成的试卷")
def download_exam(record_id: int, db: Session = Depends(get_db)):
    record = db.query(ExamRecord).get(record_id)
    if not record:
        raise HTTPException(404, "记录不存在")
    import os
    if not os.path.exists(record.file_path):
        raise HTTPException(404, "文件不存在，可能已被清理")
    return FileResponse(
        record.file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{record.title}.docx",
    )


def _generate_math_exam(req: ExamCreateRequest, db: Session) -> str:
    from ..services.math_generator import generate_math_problems
    from ..services.docx_service import build_math_docx

    problems = generate_math_problems(
        grade=req.grade,
        difficulty=req.difficulty,
        categories=req.math_categories,
        problem_types=None,
        count=req.math_count,
        include_answer=True,
        db=db,
    )
    return build_math_docx(problems, req.grade, req.difficulty, title=req.title)


def _generate_english_exam(req: ExamCreateRequest, db: Session) -> str:
    from ..services.english_generator import generate_english_exercises
    from ..services.docx_service import build_english_docx

    exercises = generate_english_exercises(
        grade=req.grade,
        book_ids=req.english_book_ids,
        word_count=req.english_word_count,
        exercise_types=req.english_types,
        db=db,
    )
    return build_english_docx(exercises, req.grade, title=req.title)
