"""试卷生成 API 路由"""
import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.exam import ExamRecord, Question
from ..schemas.exam import (
    ExamCreateRequest, ExamOut, QuestionOut,
    MarkWrongRequest, WrongPracticeRequest,
)

router = APIRouter()


@router.post("/generate", summary="生成试卷（返回下载）")
def generate_exam(req: ExamCreateRequest, db: Session = Depends(get_db)):
    """
    生成完整试卷并返回Word文档下载。
    所有题目自动保存到数据库，可后续标记错题。
    """
    if req.subject == "数学":
        filepath, questions_data = _generate_math_exam(req, db)
    elif req.subject == "英语":
        filepath, questions_data = _generate_english_exam(req, db)
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
        question_count=len(questions_data),
    )
    db.add(record)
    db.flush()

    # 保存每道题目到数据库
    for qd in questions_data:
        q = Question(
            exam_id=record.id,
            seq=qd["seq"],
            subject=req.subject,
            category=qd.get("category", ""),
            type_code=qd.get("type_code", ""),
            type_name=qd.get("type_name", ""),
            question=qd["question"],
            answer=qd.get("answer", ""),
            options_json=json.dumps(qd.get("options", []), ensure_ascii=False) if qd.get("options") else "",
            difficulty=qd.get("difficulty", 1),
        )
        db.add(q)

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


# ─── 题目查询 ───────────────────────────────────────────────

@router.get("/{exam_id}/questions", response_model=List[QuestionOut], summary="查看试卷所有题目")
def list_questions(
    exam_id: int,
    db: Session = Depends(get_db),
):
    record = db.query(ExamRecord).get(exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")
    questions = db.query(Question).filter(Question.exam_id == exam_id).order_by(Question.seq).all()
    return [
        QuestionOut(
            id=q.id, exam_id=q.exam_id, seq=q.seq, subject=q.subject,
            category=q.category, type_code=q.type_code, type_name=q.type_name,
            question=q.question, answer=q.answer, options_json=q.options_json,
            difficulty=q.difficulty, is_wrong=q.is_wrong,
            wrong_at=q.wrong_at.strftime("%Y-%m-%d %H:%M:%S") if q.wrong_at else None,
        )
        for q in questions
    ]


# ─── 错题标记 ───────────────────────────────────────────────

@router.post("/{exam_id}/mark-wrong", summary="标记错题")
def mark_wrong(
    exam_id: int,
    req: MarkWrongRequest,
    db: Session = Depends(get_db),
):
    """
    标记指定试卷中的错题为错题。
    可通过 question_ids（题目数据库ID）或 seqs（试卷内序号）指定。
    """
    record = db.query(ExamRecord).get(exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")

    now = datetime.now()
    marked = 0

    if req.question_ids:
        questions = db.query(Question).filter(
            Question.id.in_(req.question_ids),
            Question.exam_id == exam_id,
        ).all()
        for q in questions:
            q.is_wrong = True
            q.wrong_at = now
            marked += 1
    elif req.seqs:
        questions = db.query(Question).filter(
            Question.exam_id == exam_id,
            Question.seq.in_(req.seqs),
        ).all()
        for q in questions:
            q.is_wrong = True
            q.wrong_at = now
            marked += 1
    else:
        raise HTTPException(400, "请提供 question_ids 或 seqs")

    db.commit()
    return {"message": f"已标记 {marked} 道错题", "exam_id": exam_id, "marked_count": marked}


@router.post("/{exam_id}/unmark-wrong", summary="取消错题标记")
def unmark_wrong(
    exam_id: int,
    req: MarkWrongRequest,
    db: Session = Depends(get_db),
):
    """取消错题标记（已掌握的题）"""
    record = db.query(ExamRecord).get(exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")

    unmarked = 0
    if req.question_ids:
        questions = db.query(Question).filter(
            Question.id.in_(req.question_ids),
            Question.exam_id == exam_id,
        ).all()
        for q in questions:
            q.is_wrong = False
            q.wrong_at = None
            unmarked += 1
    elif req.seqs:
        questions = db.query(Question).filter(
            Question.exam_id == exam_id,
            Question.seq.in_(req.seqs),
        ).all()
        for q in questions:
            q.is_wrong = False
            q.wrong_at = None
            unmarked += 1
    else:
        raise HTTPException(400, "请提供 question_ids 或 seqs")

    db.commit()
    return {"message": f"已取消 {unmarked} 道错题标记", "unmarked_count": unmarked}


# ─── 错题列表 ───────────────────────────────────────────────

@router.get("/wrong/list", response_model=List[QuestionOut], summary="查看所有错题")
def list_wrong_questions(
    subject: str = Query(None, description="学科筛选"),
    type_code: str = Query(None, description="题型代码筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Question).filter(Question.is_wrong == True)
    if subject:
        q = q.filter(Question.subject == subject)
    if type_code:
        q = q.filter(Question.type_code == type_code)
    questions = q.order_by(Question.wrong_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return [
        QuestionOut(
            id=qq.id, exam_id=qq.exam_id, seq=qq.seq, subject=qq.subject,
            category=qq.category, type_code=qq.type_code, type_name=qq.type_name,
            question=qq.question, answer=qq.answer, options_json=qq.options_json,
            difficulty=qq.difficulty, is_wrong=qq.is_wrong,
            wrong_at=qq.wrong_at.strftime("%Y-%m-%d %H:%M:%S") if qq.wrong_at else None,
        )
        for qq in questions
    ]


# ─── 错题专项练习 ─────────────────────────────────────────────

@router.post("/wrong/practice", summary="错题专项练习（生成Word）")
def wrong_practice(req: WrongPracticeRequest, db: Session = Depends(get_db)):
    """
    从错题本中抽取题目，生成专项练习Word文档。
    支持按学科、题型筛选。
    """
    from ..services.docx_service import build_wrong_practice_docx

    q = db.query(Question).filter(Question.is_wrong == True)
    if req.subject:
        q = q.filter(Question.subject == req.subject)
    if req.type_code:
        q = q.filter(Question.type_code == req.type_code)

    all_wrong = q.order_by(Question.wrong_at.desc()).all()
    if not all_wrong:
        raise HTTPException(404, "暂无错题记录")

    # 抽取指定数量
    import random
    selected = random.sample(all_wrong, min(req.count, len(all_wrong)))
    selected.sort(key=lambda x: (x.subject, x.type_code, x.seq))

    filepath = build_wrong_practice_docx(selected, include_answer=req.include_answer)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="错题专项练习.docx",
    )


# ─── 内部生成函数 ─────────────────────────────────────────────

def _generate_math_exam(req: ExamCreateRequest, db: Session):
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
    filepath = build_math_docx(problems, req.grade, req.difficulty, title=req.title)

    # 转换为统一格式用于存储
    questions_data = []
    for i, p in enumerate(problems, 1):
        questions_data.append({
            "seq": i,
            "category": p.category,
            "type_code": p.type_code,
            "type_name": p.type_name,
            "question": p.question,
            "answer": p.answer,
            "options": None,
            "difficulty": p.difficulty,
        })
    return filepath, questions_data


def _generate_english_exam(req: ExamCreateRequest, db: Session):
    from ..services.english_generator import generate_english_exam, TYPE_NAMES
    from ..services.docx_service import build_english_docx

    exercises = generate_english_exam(
        grade=req.grade,
        book_ids=req.english_book_ids,
        count_per_type=req.english_count_per_type,
        exercise_types=req.english_types,
        db=db,
    )
    filepath = build_english_docx(exercises, req.grade, title=req.title)

    # 转换为统一格式用于存储
    questions_data = []
    seq = 0
    for etype, items in exercises.items():
        type_name = TYPE_NAMES.get(etype, etype)
        for item in items:
            seq += 1
            questions_data.append({
                "seq": seq,
                "category": "英语",
                "type_code": etype,
                "type_name": type_name,
                "question": item["question"],
                "answer": item["answer"],
                "options": item.get("options"),
                "difficulty": 1,
            })
    return filepath, questions_data
