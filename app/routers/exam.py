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
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.exam import ExamRecord, Question, WrongRecord, ExamAttempt, AttemptAnswer
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
    elif req.subject == "语文":
        filepath, questions_data = _generate_chinese_exam(req, db)
    else:
        raise HTTPException(400, "学科仅支持：数学 / 英语 / 语文")

    from datetime import datetime as _dt
    title = req.title or f"{_dt.now().strftime('%y%m%d%H%M%S')}{req.subject}{len(questions_data)}题{req.difficulty}卷"
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
            image_path=qd.get("image_path", ""),
            audio_path=qd.get("audio_path", ""),
            difficulty=qd.get("difficulty", 1),
        ))

    db.commit()

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{title}.docx",
        headers={"X-Exam-Id": str(record.id)},
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
            question_count=r.question_count, file_path=r.file_path or "",
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
        or_(WrongRecord.is_mastered.is_(None), WrongRecord.is_mastered != True),
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


class WrongPracticeQuizRequest(BaseModel):
    """错题在线练习抽题（JSON，供前端直接答题）"""
    user_id: str = Field(..., max_length=64, description="用户标识")
    subject: Optional[str] = Field(None, description="学科筛选：数学/英语，不填则混合")
    count: int = Field(10, ge=1, le=50, description="练习题数（默认 10）")


def _parse_options_json(options_json: Optional[str]) -> list:
    """解析选项 JSON 字符串，失败返回空列表"""
    if not options_json:
        return []
    try:
        data = json.loads(options_json)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


@router.post("/wrong/practice-quiz", summary="错题在线练习抽题（JSON 直接答题）")
def wrong_practice_quiz(req: WrongPracticeQuizRequest, db: Session = Depends(get_db)):
    """从用户未掌握的错题中随机抽 count 道（默认 10），返回可直接答题的 JSON。

    - 范围为错题本中当前学科的错题类型（未掌握记录，含选项/答案/题型）
    - 每道题带 record_id，前端答完用 /api/study/practice-submit 回写
      （连续 3 次答对自动掌握，答错重新激活）
    """
    q = db.query(WrongRecord).filter(
        WrongRecord.user_id == req.user_id,
        or_(WrongRecord.is_mastered.is_(None), WrongRecord.is_mastered != True),
    ).join(Question)

    if req.subject:
        q = q.filter(Question.subject == req.subject)

    all_wrong = q.order_by(WrongRecord.wrong_at.desc()).all()
    if not all_wrong:
        raise HTTPException(404, "暂无错题可练习（或全部已掌握）")

    selected = random.sample(all_wrong, min(req.count, len(all_wrong)))
    selected.sort(key=lambda wr: (wr.question.subject, wr.question.type_code, wr.question.seq))

    questions = [{
        "qid": wr.question_id,
        "kind": "exam",
        "record_id": wr.id,
        "question": wr.question.question,
        "options": _parse_options_json(wr.question.options_json),
        "answer": wr.question.answer,
        "explanation": "",
        "type_name": wr.question.type_name or "",
        "subject": wr.question.subject,
        "exam_id": wr.question.exam_id,
    } for wr in selected]
    return {"count": len(questions), "questions": questions}


# ═══════════════════════════════════════════════════════════
# 在线做题
# ═══════════════════════════════════════════════════════════

@router.post("/submit-answers", summary="提交答案（在线做题判分）")
def submit_answers(req: dict, db: Session = Depends(get_db)):
    """
    在线做题提交。
    请求体: {
        "user_id": "小明",
        "exam_id": 1,
        "answers": [{"question_id": 1, "user_answer": "xxx"}, ...]
    }
    返回: 每题对错 + 总分 + 自动将错题加入错题本
    """
    user_id = req.get("user_id", "")
    exam_id = req.get("exam_id")
    answers = req.get("answers", [])

    if not user_id or not exam_id or not answers:
        raise HTTPException(400, "缺少 user_id / exam_id / answers")

    record = db.query(ExamRecord).get(exam_id)
    if not record:
        raise HTTPException(404, "试卷不存在")

    now = datetime.now()
    results = []
    correct_count = 0
    wrong_seqs = []
    wrong_ids: dict = {}

    for item in answers:
        qid = item.get("question_id")
        user_ans = str(item.get("user_answer", "")).strip()
        q = db.query(Question).filter(Question.id == qid, Question.exam_id == exam_id).first()
        if not q:
            continue

        # 判分：选择题精确匹配，其他去空格后包含匹配
        correct_ans = q.answer.strip()
        is_correct = _check_answer(user_ans, correct_ans, q.options_json)

        if is_correct:
            correct_count += 1
        else:
            wrong_seqs.append(q.seq)
            # 自动加入错题本
            existing = db.query(WrongRecord).filter(
                WrongRecord.user_id == user_id,
                WrongRecord.question_id == q.id,
            ).first()
            if existing:
                existing.is_mastered = False
                existing.mastered_at = None
                existing.wrong_at = now
                wrong_ids[q.id] = existing.id
            else:
                rec = WrongRecord(user_id=user_id, question_id=q.id, wrong_at=now)
                db.add(rec)
                db.flush()  # 立即取得 id，供前端错因自评
                wrong_ids[q.id] = rec.id

        results.append({
            "question_id": q.id,
            "seq": q.seq,
            "question": q.question,
            "correct_answer": correct_ans,
            "user_answer": user_ans,
            "is_correct": is_correct,
        })

    db.commit()

    total = len(results)
    score = round(correct_count / total * 100, 1) if total > 0 else 0

    # 保存做题记录
    attempt = ExamAttempt(
        user_id=user_id,
        exam_id=exam_id,
        score=int(score),
        total=total,
        correct=correct_count,
        wrong=total - correct_count,
        duration_sec=req.get("duration_sec", 0),
    )
    db.add(attempt)
    db.flush()

    for r in results:
        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=r["question_id"],
            user_answer=r["user_answer"],
            is_correct=r["is_correct"],
        ))
    db.commit()

    return {
        "exam_id": exam_id,
        "attempt_id": attempt.id,
        "user_id": user_id,
        "total": total,
        "correct": correct_count,
        "wrong": total - correct_count,
        "score": score,
        "results": results,
        "wrong_ids": wrong_ids,
    }


@router.get("/wrong/stats", summary="错题分析（按题型统计）")
def wrong_stats(
    user_id: str = Query(..., description="用户标识"),
    subject: str = Query(None, description="学科筛选"),
    db: Session = Depends(get_db),
):
    """
    错题分析：按题型分组统计错题数量、已掌握数量、练习次数。
    """
    q = db.query(WrongRecord).filter(WrongRecord.user_id == user_id).join(Question)
    if subject:
        q = q.filter(Question.subject == subject)

    records = q.all()
    if not records:
        return {"total_wrong": 0, "total_mastered": 0, "by_type": []}

    # 按 type_code 分组
    from collections import defaultdict
    groups = defaultdict(lambda: {"wrong": 0, "mastered": 0, "practice_total": 0, "type_name": "", "subject": ""})
    for wr in records:
        qc = wr.question.type_code or "unknown"
        g = groups[qc]
        g["type_name"] = wr.question.type_name or qc
        g["subject"] = wr.question.subject
        g["practice_total"] += wr.practice_count
        if wr.is_mastered:
            g["mastered"] += 1
        else:
            g["wrong"] += 1

    by_type = []
    for code, g in sorted(groups.items(), key=lambda x: -x[1]["wrong"]):
        by_type.append({
            "type_code": code,
            "type_name": g["type_name"],
            "subject": g["subject"],
            "wrong_count": g["wrong"],
            "mastered_count": g["mastered"],
            "practice_total": g["practice_total"],
        })

    total_wrong = sum(g["wrong"] for g in groups.values())
    total_mastered = sum(g["mastered"] for g in groups.values())
    return {"total_wrong": total_wrong, "total_mastered": total_mastered, "by_type": by_type}


def _check_answer(user_ans: str, correct_ans: str, options_json: str) -> bool:
    """判断答案是否正确"""
    if not user_ans:
        return False
    ua = user_ans.strip().lower()
    ca = correct_ans.strip().lower()

    # 选择题：用户可能只输入了字母 A/B/C/D
    if options_json:
        # 正确答案可能是 "A" 或 "B" 等
        if len(ca) == 1 and ca in "abcd":
            return ua == ca or ua == ca.upper()
        # 选项里匹配
        if ua == ca:
            return True

    # 精确匹配
    if ua == ca:
        return True

    # 数字答案：提取数字比较
    import re
    ua_nums = re.findall(r'-?\d+\.?\d*', ua)
    ca_nums = re.findall(r'-?\d+\.?\d*', ca)
    if ca_nums and ua_nums:
        # 如果正确答案只有一个核心数字，用户答案包含即可
        if len(ca_nums) == 1 and ca_nums[0] in ua_nums:
            return True
        if ua_nums == ca_nums:
            return True

    return False


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
        cause=wr.cause or "",
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
            "image_path": p.image_path,
        })
    return filepath, questions_data


def _build_typed_paper(target: int, types_used: List[str], gen_fn) -> Dict[str, list]:
    """按目标总题数精确生成分题型试卷（英语/语文共用）。

    - target < 题型数：只使用前 target 个题型，每题型 1 题
    - 否则：带余数均分（前 rem 个题型各多 1 题），保证总数 == target
    - 生成结果按题目文本去重；不足时向所有题型追加补齐（最多 3 轮）
    - 超出时从尾部裁剪（每题型至少保留 1 题）；空题型过滤
    gen_fn(types: List[str], count_per_type: int) -> Dict[str, list]
    """
    if target < 1:
        return {}
    if len(types_used) > target:
        types_used = types_used[:target]

    # 带余数均分配额
    base, rem = divmod(target, len(types_used)) if types_used else (0, 0)
    quotas = {t: base + (1 if i < rem else 0) for i, t in enumerate(types_used)}

    # 相同配额分组调用，减少生成器调用次数
    groups = {}
    for t, q in quotas.items():
        groups.setdefault(q, []).append(t)

    result: Dict[str, list] = {}
    seen = {t: set() for t in types_used}
    for q, types in groups.items():
        for etype, items in gen_fn(types, q).items():
            pool = result.setdefault(etype, [])
            if etype not in seen:
                seen[etype] = set()
            for it in items:
                qtext = it.get("question", "")
                if qtext and qtext in seen[etype]:
                    continue
                if qtext:
                    seen[etype].add(qtext)
                pool.append(it)

    # 总数不足：向各题型追加补齐（去重），最多 3 轮
    total = sum(len(v) for v in result.values())
    for _ in range(3):
        if total >= target:
            break
        need = target - total
        added = 0
        for etype, items in gen_fn(types_used, need).items():
            pool = result.setdefault(etype, [])
            if etype not in seen:
                seen[etype] = set()
            for it in items:
                qtext = it.get("question", "")
                if qtext and qtext in seen[etype]:
                    continue
                if qtext:
                    seen[etype].add(qtext)
                pool.append(it)
                added += 1
                if added >= need:
                    break
            if added >= need:
                break
        if added == 0:
            break
        total += added

    # 总数超出：从尾部裁剪（每题型至少保留 1 题）
    total = sum(len(v) for v in result.values())
    if total > target:
        overflow = total - target
        for t in reversed(list(result.keys())):
            if overflow <= 0:
                break
            lst = result[t]
            while len(lst) > 1 and overflow > 0:
                lst.pop()
                overflow -= 1

    return {k: v for k, v in result.items() if v}


def _generate_english_exam(req: ExamCreateRequest, db: Session):
    """生成英语试卷，返回 (文件路径, 题目数据列表)"""
    from ..services.english_generator import generate_english_exam, TYPE_NAMES, ALL_EXERCISE_TYPES
    from ..services.docx_service import build_english_docx

    # 确定实际使用的题型列表
    types_used = req.english_types if req.english_types else ALL_EXERCISE_TYPES[:]

    def _gen(types, count):
        return generate_english_exam(
            grade=req.grade,
            book_ids=req.english_book_ids,
            count_per_type=count,
            exercise_types=types,
            db=db,
        )

    exercises = _build_typed_paper(req.english_count, types_used, _gen)
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
                "audio_path": item.get("audio_path", ""),
            })
    return filepath, questions_data


# ═══════════════════════════════════════════════════════════
# 做题记录查询
# ═══════════════════════════════════════════════════════════

@router.get("/attempts/list", summary="用户做题记录列表")
def list_attempts(
    user_id: str = Query(..., description="用户标识"),
    subject: str = Query(None, description="学科筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(ExamAttempt).filter(ExamAttempt.user_id == user_id)
    if subject:
        q = q.join(ExamRecord).filter(ExamRecord.subject == subject)
    attempts = q.order_by(ExamAttempt.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    # 批量取试卷标题与学科，避免 N+1
    exam_ids = {a.exam_id for a in attempts if a.exam_id}
    exam_map = {}
    if exam_ids:
        for r in db.query(ExamRecord).filter(ExamRecord.id.in_(exam_ids)).all():
            exam_map[r.id] = r
    return [
        {
            "id": a.id,
            "exam_id": a.exam_id,
            "score": a.score,
            "total": a.total,
            "correct": a.correct,
            "wrong": a.wrong,
            "duration_sec": a.duration_sec,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "exam_title": exam_map[a.exam_id].title if a.exam_id in exam_map else "",
            "subject": exam_map[a.exam_id].subject if a.exam_id in exam_map else "",
        }
        for a in attempts
    ]


@router.get("/attempts/{attempt_id}", summary="单次做题详情")
def get_attempt_detail(attempt_id: int, db: Session = Depends(get_db)):
    attempt = db.query(ExamAttempt).get(attempt_id)
    if not attempt:
        raise HTTPException(404, "记录不存在")
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    detail = []
    for aa in answers:
        q = db.query(Question).get(aa.question_id)
        detail.append({
            "question_id": aa.question_id,
            "user_answer": aa.user_answer,
            "is_correct": aa.is_correct,
            "question": q.question if q else "",
            "correct_answer": q.answer if q else "",
            "type_name": q.type_name if q else "",
        })
    return {
        "id": attempt.id,
        "exam_id": attempt.exam_id,
        "user_id": attempt.user_id,
        "score": attempt.score,
        "total": attempt.total,
        "correct": attempt.correct,
        "wrong": attempt.wrong,
        "created_at": attempt.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "answers": detail,
    }


# ═══════════════════════════════════════════════════════════
# 批量标记掌握（不依赖 exam_id）
# ═══════════════════════════════════════════════════════════

@router.post("/wrong/batch-master", summary="批量标记错题已掌握")
def batch_master(req: dict, db: Session = Depends(get_db)):
    """
    批量将错题标记为已掌握（不需要 exam_id）。
    请求体: { "user_id": "xxx", "question_ids": [1, 2, 3] }
    """
    user_id = req.get("user_id", "")
    question_ids = req.get("question_ids", [])
    if not user_id or not question_ids:
        raise HTTPException(400, "缺少 user_id 或 question_ids")

    now = datetime.now()
    mastered = 0
    for qid in question_ids:
        wr = db.query(WrongRecord).filter(
            WrongRecord.user_id == user_id,
            WrongRecord.question_id == qid,
        ).first()
        if wr and not wr.is_mastered:
            wr.is_mastered = True
            wr.mastered_at = now
            mastered += 1
    db.commit()
    return {"message": f"已标记 {mastered} 题为已掌握", "mastered_count": mastered}


def _generate_chinese_exam(req: ExamCreateRequest, db: Session):
    """生成语文试卷，返回 (文件路径, 题目数据列表)"""
    from ..services.chinese_generator import generate_chinese_exam, TYPE_NAMES, ALL_EXERCISE_TYPES
    from ..services.docx_service import build_english_docx

    types_used = req.english_types if req.english_types else ALL_EXERCISE_TYPES[:]

    def _gen(types, count):
        return generate_chinese_exam(
            grade=req.grade,
            count_per_type=count,
            exercise_types=types,
            db=db,
        )

    exercises = _build_typed_paper(req.english_count, types_used, _gen)
    filepath = build_english_docx(
        exercises, req.grade, title=req.title,
        type_names=TYPE_NAMES, filename_prefix="语文",
    )

    questions_data = []
    seq = 0
    for etype, items in exercises.items():
        type_name = TYPE_NAMES.get(etype, etype)
        for item in items:
            seq += 1
            questions_data.append({
                "seq": seq,
                "category": "语文",
                "type_code": etype,
                "type_name": type_name,
                "question": item["question"],
                "answer": item["answer"],
                "options": item.get("options"),
                "difficulty": 1,
            })
    return filepath, questions_data
