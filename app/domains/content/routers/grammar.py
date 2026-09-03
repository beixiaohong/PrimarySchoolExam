"""英语语法练习 API 路由

提供语法点（GrammarPoint）与练习题（GrammarExercise）的管理、出题与判分：
- 管理端：语法点/练习题的增删查（code 唯一，题型 choice/fill/transform/correct）
- 练习端：按年级/语法点随机出题、提交判分（choice 比字母，其余走 fill_answer_correct 容错）
- 统计：各语法点/题型的题目数量
本模块接口无需家长密码，均为学习/管理数据操作，无金币/钻石发放。
"""
import json
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.grammar import GrammarPoint, GrammarExercise

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════

class GrammarPointCreate(BaseModel):
    name: str
    code: str
    grade: int = 3
    category: str = "时态"
    description: str = ""
    examples: str = ""


class GrammarPointOut(BaseModel):
    id: int
    name: str
    code: str
    grade: int
    category: str
    description: str
    examples: str
    exercise_count: int = 0


class GrammarExerciseCreate(BaseModel):
    grammar_point_id: int
    grade: int = 3
    exercise_type: str  # choice / fill / transform / correct
    question: str
    options: str = ""  # JSON array string for choice type
    answer: str
    explanation: str = ""
    difficulty: int = 1


class GrammarExerciseOut(BaseModel):
    id: int
    grammar_point_id: int
    grammar_point_name: str = ""
    grade: int
    exercise_type: str
    question: str
    options: list = []
    answer: str
    explanation: str
    difficulty: int


class GrammarQuizRequest(BaseModel):
    user_id: str
    grade: int = 6
    grammar_point_id: Optional[int] = None
    count: int = 10
    exercise_types: Optional[List[str]] = None


class GrammarSubmitItem(BaseModel):
    exercise_id: int
    user_answer: str


class GrammarSubmitRequest(BaseModel):
    user_id: str
    results: List[GrammarSubmitItem]


# ═══════════════════════════════════════════════════════════
# 语法点管理
# ═══════════════════════════════════════════════════════════

@router.post("/points", summary="添加语法点")
def add_grammar_point(req: GrammarPointCreate, db: Session = Depends(get_db)):
    """新增语法点（code 唯一）。请求：{name, code, grade, category, description, examples}；返回 GrammarPointOut。
    副作用：校验 code/name 不重复，写 grammar_points 并落库。"""
    existing = db.query(GrammarPoint).filter(GrammarPoint.code == req.code).first()
    if existing:
        raise HTTPException(400, f"语法点编码 '{req.code}' 已存在")
    existing_name = db.query(GrammarPoint).filter(GrammarPoint.name == req.name).first()
    if existing_name:
        raise HTTPException(400, f"语法点 '{req.name}' 已存在")
    point = GrammarPoint(
        name=req.name, code=req.code, grade=req.grade,
        category=req.category, description=req.description, examples=req.examples,
    )
    db.add(point)
    db.commit()
    db.refresh(point)
    count = db.query(GrammarExercise).filter(GrammarExercise.grammar_point_id == point.id).count()
    return GrammarPointOut(
        id=point.id, name=point.name, code=point.code, grade=point.grade,
        category=point.category, description=point.description, examples=point.examples,
        exercise_count=count,
    )


@router.get("/points", summary="获取语法点列表")
def list_grammar_points(
    grade: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """语法点列表（可按年级≤/分类筛选）。查询参数：grade, category；返回 GrammarPointOut[]（含 exercise_count）。只读。"""
    q = db.query(GrammarPoint)
    if grade:
        q = q.filter(GrammarPoint.grade <= grade)
    if category:
        q = q.filter(GrammarPoint.category == category)
    points = q.order_by(GrammarPoint.grade, GrammarPoint.id).all()
    result = []
    for p in points:
        count = db.query(GrammarExercise).filter(GrammarExercise.grammar_point_id == p.id).count()
        result.append(GrammarPointOut(
            id=p.id, name=p.name, code=p.code, grade=p.grade,
            category=p.category, description=p.description, examples=p.examples,
            exercise_count=count,
        ))
    return result


@router.get("/points/{point_id}", summary="获取语法点详情")
def get_grammar_point(point_id: int, db: Session = Depends(get_db)):
    """语法点详情（含练习题数）。路径参数：point_id；不存在抛 404。只读。"""
    point = db.query(GrammarPoint).filter(GrammarPoint.id == point_id).first()
    if not point:
        raise HTTPException(404, "语法点不存在")
    count = db.query(GrammarExercise).filter(GrammarExercise.grammar_point_id == point.id).count()
    return GrammarPointOut(
        id=point.id, name=point.name, code=point.code, grade=point.grade,
        category=point.category, description=point.description, examples=point.examples,
        exercise_count=count,
    )


# ═══════════════════════════════════════════════════════════
# 练习题管理
# ═══════════════════════════════════════════════════════════

@router.post("/exercises", summary="添加语法练习题")
def add_exercise(req: GrammarExerciseCreate, db: Session = Depends(get_db)):
    """新增语法练习题。请求：{grammar_point_id, grade, exercise_type, question, options?, answer, explanation?, difficulty}；返回 {id, message}。
    副作用：校验所属语法点存在、题型合法，写 grammar_exercises 并落库。"""
    point = db.query(GrammarPoint).filter(GrammarPoint.id == req.grammar_point_id).first()
    if not point:
        raise HTTPException(404, "语法点不存在")
    valid_types = ("choice", "fill", "transform", "correct")
    if req.exercise_type not in valid_types:
        raise HTTPException(400, f"题型无效，可选：{', '.join(valid_types)}")
    exercise = GrammarExercise(
        grammar_point_id=req.grammar_point_id,
        grade=req.grade,
        exercise_type=req.exercise_type,
        question=req.question,
        options=req.options,
        answer=req.answer,
        explanation=req.explanation,
        difficulty=req.difficulty,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return {"id": exercise.id, "message": "添加成功"}


@router.get("/exercises", summary="获取练习题列表")
def list_exercises(
    grammar_point_id: Optional[int] = Query(None),
    grade: Optional[int] = Query(None),
    exercise_type: Optional[str] = Query(None),
    difficulty: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """练习题列表（多条件筛选 + 分页）。查询参数：grammar_point_id/grade/exercise_type/difficulty/page/page_size；返回 GrammarExerciseOut[]。只读。"""
    q = db.query(GrammarExercise)
    if grammar_point_id:
        q = q.filter(GrammarExercise.grammar_point_id == grammar_point_id)
    if grade:
        q = q.filter(GrammarExercise.grade <= grade)
    if exercise_type:
        q = q.filter(GrammarExercise.exercise_type == exercise_type)
    if difficulty:
        q = q.filter(GrammarExercise.difficulty == difficulty)
    exercises = q.order_by(GrammarExercise.grade, GrammarExercise.id).offset((page - 1) * page_size).limit(page_size).all()
    result = []
    for e in exercises:
        point = db.query(GrammarPoint).filter(GrammarPoint.id == e.grammar_point_id).first()
        opts = []
        if e.options:
            try:
                opts = json.loads(e.options)
            except (json.JSONDecodeError, TypeError):
                opts = []
        result.append(GrammarExerciseOut(
            id=e.id, grammar_point_id=e.grammar_point_id,
            grammar_point_name=point.name if point else "",
            grade=e.grade, exercise_type=e.exercise_type,
            question=e.question, options=opts,
            answer=e.answer, explanation=e.explanation,
            difficulty=e.difficulty,
        ))
    return result


# ═══════════════════════════════════════════════════════════
# 出题 / 练习
# ═══════════════════════════════════════════════════════════

@router.post("/quiz", summary="生成语法练习")
def generate_grammar_quiz(req: GrammarQuizRequest, db: Session = Depends(get_db)):
    """根据年级和语法点随机生成练习题"""
    q = db.query(GrammarExercise).filter(GrammarExercise.grade <= req.grade)
    if req.grammar_point_id:
        q = q.filter(GrammarExercise.grammar_point_id == req.grammar_point_id)
    if req.exercise_types:
        q = q.filter(GrammarExercise.exercise_type.in_(req.exercise_types))

    all_exercises = q.all()
    if not all_exercises:
        raise HTTPException(404, f"暂无符合条件的语法练习题")

    random.shuffle(all_exercises)
    selected = all_exercises[:req.count]

    questions = []
    for e in selected:
        point = db.query(GrammarPoint).filter(GrammarPoint.id == e.grammar_point_id).first()
        opts = []
        if e.options:
            try:
                opts = json.loads(e.options)
            except (json.JSONDecodeError, TypeError):
                opts = []
        questions.append({
            "exercise_id": e.id,
            "grammar_point_name": point.name if point else "",
            "exercise_type": e.exercise_type,
            "question": e.question,
            "options": opts,
            "answer": e.answer,
            "explanation": e.explanation,
            "difficulty": e.difficulty,
        })

    return {"count": len(questions), "questions": questions}


@router.post("/submit", summary="提交语法练习答案")
def submit_grammar_answers(req: GrammarSubmitRequest, db: Session = Depends(get_db)):
    """批改语法练习答案"""
    results = []
    correct_count = 0

    for item in req.results:
        exercise = db.query(GrammarExercise).filter(GrammarExercise.id == item.exercise_id).first()
        if not exercise:
            results.append({
                "exercise_id": item.exercise_id,
                "status": "not_found",
                "correct": False,
            })
            continue

        user_ans = item.user_answer.strip().lower()
        correct_ans = exercise.answer.strip().lower()

        # 选择题只比较字母
        if exercise.exercise_type == "choice":
            is_correct = user_ans == correct_ans
        else:
            # 填空题：忽略大小写和首尾空格，并支持算式/格式容错（与前端即时反馈一致）
            from app.domains.assessment.services.answer_check import fill_answer_correct
            is_correct = fill_answer_correct(user_ans, correct_ans)

        if is_correct:
            correct_count += 1

        results.append({
            "exercise_id": item.exercise_id,
            "correct": is_correct,
            "user_answer": item.user_answer,
            "correct_answer": exercise.answer,
            "explanation": exercise.explanation,
            "question": exercise.question,
        })

    total = len(req.results)
    score = round(correct_count / total * 100) if total > 0 else 0

    return {
        "total": total,
        "correct": correct_count,
        "wrong": total - correct_count,
        "score": score,
        "results": results,
    }


# ═══════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════

@router.get("/stats", summary="语法练习统计")
def grammar_stats(
    grade: int = Query(6),
    db: Session = Depends(get_db),
):
    """统计各语法点的题目数量"""
    points = db.query(GrammarPoint).filter(GrammarPoint.grade <= grade).all()
    stats = []
    total_exercises = 0
    for p in points:
        count = db.query(GrammarExercise).filter(
            GrammarExercise.grammar_point_id == p.id
        ).count()
        total_exercises += count
        stats.append({
            "grammar_point_id": p.id,
            "name": p.name,
            "category": p.category,
            "exercise_count": count,
        })

    by_type = []
    for t in ("choice", "fill", "transform", "correct"):
        count = db.query(GrammarExercise).filter(
            GrammarExercise.exercise_type == t,
            GrammarExercise.grade <= grade,
        ).count()
        by_type.append({"type": t, "count": count})

    return {
        "total_points": len(points),
        "total_exercises": total_exercises,
        "by_point": stats,
        "by_type": by_type,
    }
