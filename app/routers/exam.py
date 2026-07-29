"""试卷生成 API 路由

功能：
  - 生成数学/英语试卷（Word下载），题目自动入库（试卷不绑定用户）
  - 查看试卷记录、试卷题目
  - 标记/取消错题（按用户）、标记已掌握
  - 错题列表查询（按用户）
  - 错题专项练习（按用户，生成Word）

设计原则：
  试卷和题目是公共资源（一份卷可给多人用），
  错题记录绑定用户（每人有独立错题本）。
"""
import json
import random
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.exam import ExamRecord, Question, WrongRecord
from ..schemas.exam import (
    ExamCreateRequest, ExamOut, QuestionOut, WrongRecordOut,
    MarkWrongRequest, WrongPracticeRequest,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# 试卷生成（公共，不绑定用户）
# ═══════════════════════════════════════════════════════════

@router.post("/generate", summary="生成试卷（Word下载，题目自动入库）")
def generate_exam(req: ExamCreateRequest, db: Session = Depends(get_db)):
    """
    生成完整试卷并返回Word文档下载。
    所有题目自动保存到 questions 表。
    试卷为公共资源，不绑定用户。
    """
    if req.subject == "数学":
        filepath, questions_data = _generate_math_exam(req, db)
    elif req.subject == "英语":
        filepath, questions_data = _generate_english_exam(req, db)
    else:
        raise HTTPException(400, "学科仅支持：数学 / 英语")

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

    # 逐题入库
    for qd in questions_data:
        db.add(Question(
            exam_id=record.id,
            seq=qd["seq"],
            subject=req.subject,
            category=qd.get("category", ""),
            type_code=qd.get("type_code", ""),
            type_name=qd.get("type_name", ""),
            question=qd["question"],
            answer=qd.get("answer", ""),
            options_json=json.dumps(qd["options"], ensure_ascii=False) if qd.get("options") else "",
            difficulty=qd.get("difficulty", 1),
        ))

    db.commit()

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{title}.docx",
    )


# ═══════════════════════════════════════════════════════════
# 试卷记录查询
# ═══════════════════════════════════════════════════════════

@router.get("/records", response_model=List[ExamOut], summary="试卷生成记录")
def list_records(
    subject: str = Query(None, description="学科筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(ExamRecord)
    if subject:
        q = q.filter(ExamRecord.subject == subject)
    records = q.order_by(ExamRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return [
        ExamOut(
            id=r.id, subject=r.subject, title=r.title,
            grade=r.grade, difficulty=r.difficulty,
            question_count=r.question_count, file_path=r.file_path,
            created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
        for r in records
    ]


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


# ═══════════════════════════════════════════════════════════
# 题目查询
# ═══════════════════════════════════════════════════════════

@router.get("/{exam_id}/questions", response_model=List[QuestionOut], summary="查看试卷所有题目")
def list_questions(exam_id: int, db: Session = Depends(get_db)):
    record = db.query(ExamRecord).get(exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")
    questions = db.query(Question).filter(
        Question.exam_id == exam_id
    ).order_by(Question.seq).all()
    return questions


# ═══════════════════════════════════════════════════════════
# 错题管理（按用户）
# ═══════════════════════════════════════════════════════════

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
            mastered += 1
    db.commit()
    return {"message": f"已标记 {mastered} 题为已掌握", "mastered_count": mastered}


# ═══════════════════════════════════════════════════════════
# 错题列表
# ═══════════════════════════════════════════════════════════

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
    return [_wrong_record_to_out(wr) for wr in records]


# ═══════════════════════════════════════════════════════════
# 错题专项练习
# ═══════════════════════════════════════════════════════════

@router.post("/wrong/practice", summary="错题专项练习（生成Word下载）")
def wrong_practice(req: WrongPracticeRequest, db: Session = Depends(get_db)):
    """
    从用户的错题本中抽取题目，生成专项练习Word文档。
    - 已标记"已掌握"的题目不会被抽取
    - 支持按学科、题型筛选（数学/英语均可）
    - 每次练习后自动累加 practice_count
    """
    from ..services.docx_service import build_wrong_practice_docx

    q = db.query(WrongRecord).filter(
        WrongRecord.user_id == req.user_id,
        WrongRecord.is_mastered == False,
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


# ═══════════════════════════════════════════════════════════
# 内部工具函数
# ═══════════════════════════════════════════════════════════

def _locate_questions(db: Session, exam_id: int, question_ids: list = None, seqs: list = None) -> list:
    """根据 question_ids 或 seqs 定位题目"""
    record = db.query(ExamRecord).get(exam_id)
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


def _wrong_record_to_out(wr: WrongRecord) -> WrongRecordOut:
    """WrongRecord ORM → WrongRecordOut（展开题目信息）"""
    q = wr.question
    return WrongRecordOut(
        id=wr.id,
        user_id=wr.user_id,
        question_id=wr.question_id,
        is_mastered=wr.is_mastered,
        practice_count=wr.practice_count,
        wrong_at=wr.wrong_at.strftime("%Y-%m-%d %H:%M:%S") if wr.wrong_at else None,
        mastered_at=wr.mastered_at.strftime("%Y-%m-%d %H:%M:%S") if wr.mastered_at else None,
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


def _generate_math_exam(req: ExamCreateRequest, db: Session):
    """生成数学试卷，返回 (文件路径, 题目数据列表)"""
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
    """生成英语试卷，返回 (文件路径, 题目数据列表)"""
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
