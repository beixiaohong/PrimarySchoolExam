"""试卷记录、下载与题目查询端点"""
import os
from typing import List

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import router
from app.database import get_db
from app.models.exam import ExamRecord, Question
from app.schemas.exam import ExamOut, QuestionOut


@router.get("/records", response_model=List[ExamOut], summary="试卷生成记录")
def list_records(
    subject: str = Query(None, description="学科筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """分页查询已生成试卷（公共资源）的记录列表，按生成时间倒序。

    参数：subject 可选学科筛选；page/page_size 分页。
    返回试卷概要数组（id/学科/标题/年级/难度/题数/文件路径/生成时间）。
    """
    q = db.query(ExamRecord)
    if subject:
        q = q.filter(ExamRecord.subject == subject)
    records = q.order_by(ExamRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return [
        ExamOut(
            id=r.id, subject=r.subject, title=r.title,
            grade=r.grade, difficulty=r.difficulty,
            question_count=r.question_count, file_path=r.file_path or "",
            created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        for r in records
    ]


@router.get("/download/{record_id}", summary="下载已生成的试卷")
def download_exam(record_id: int, db: Session = Depends(get_db)):
    """下载已生成试卷的 Word 文档。

    参数：record_id 试卷记录 ID（路径参数）。记录不存在或文件缺失返回 404。
    返回 word 文档文件响应（.docx）。
    """
    record = db.get(ExamRecord, record_id)
    if not record:
        raise HTTPException(404, "记录不存在")
    if not os.path.exists(record.file_path):
        raise HTTPException(404, "文件不存在，可能已被清理")
    return FileResponse(
        record.file_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{record.title}.docx",
    )


@router.get("/{exam_id}/questions", response_model=List[QuestionOut], summary="查看试卷所有题目")
def list_questions(exam_id: int, db: Session = Depends(get_db)):
    """查询某份试卷包含的全部题目，按题号（seq）顺序返回。

    参数：exam_id 试卷记录 ID（路径参数）。试卷不存在返回 404。
    返回题目对象数组（含题干/答案/选项/题型等）。
    """
    record = db.get(ExamRecord, exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")
    questions = db.query(Question).filter(
        Question.exam_id == exam_id
    ).order_by(Question.seq).all()
    return questions


__all__ = ["list_records", "download_exam", "list_questions"]
