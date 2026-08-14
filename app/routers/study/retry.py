"""错题变式重练、逐题判分相关端点与模型"""
import json
from typing import List, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import router
from app.database import get_db, random_order
from app.models.study_error import StudyError
from app.models.exam import WrongRecord, Question


class RetryRequest(BaseModel):
    user_id: str
    kind: str  # exam / study
    record_id: int
    count: int = 3


@router.post("/retry", summary="错题变式重练（生成相似题）")
def retry_wrong(req: RetryRequest, db: Session = Depends(get_db)):
    """根据错题类型生成同考点的变式题：

    - exam 试卷错题：同学科 + 同题型（type_code）随机抽题
    - study 语法错题：同语法点随机抽题
    - study 古诗文错题：同篇目其他句子生成默写
    统一返回 { questions: [{qid, question, options, answer, explanation, type_name, extra}] }，
    前端本地判分，答错的题可再次回写错题本。
    """
    import random as _random

    if req.kind == "exam":
        wr = db.query(WrongRecord).filter(
            WrongRecord.id == req.record_id,
            WrongRecord.user_id == req.user_id,
        ).first()
        if not wr:
            raise HTTPException(404, "试卷错题记录不存在")
        if wr.is_unanswered:
            raise HTTPException(400, "未作答的题请先在错题本中作答，不能直接修正")
        q = wr.question
        from app.models.exam import Question as Q
        candidates = db.query(Q).filter(
            Q.subject == q.subject,
            Q.type_code == q.type_code,
            Q.id != q.id,
        ).order_by(random_order()).limit(req.count).all()
        if len(candidates) < req.count:
            extra = db.query(Q).filter(
                Q.subject == q.subject,
                Q.id != q.id,
                Q.id.notin_([c.id for c in candidates]),
            ).order_by(random_order()).limit(req.count - len(candidates)).all()
            candidates = candidates + extra
        questions = [{
            "qid": c.id,
            "kind": "exam",
            "question": c.question,
            "options": _parse_options(c.options_json),
            # 防刷：不下发正确答案，逐题判分走 /api/study/check-answer
            "explanation": "",
            "type_name": c.type_name or "",
            "image_path": c.image_path or "",
            "exam_id": c.exam_id,
        } for c in candidates]
        return {"kind": "exam", "sub_kind": "exam", "module_name": q.type_name or "同类题",
                "count": len(questions), "questions": questions}

    # ── 学习错题 ──
    e = db.query(StudyError).filter(
        StudyError.id == req.record_id,
        StudyError.user_id == req.user_id,
    ).first()
    if not e:
        raise HTTPException(404, "学习错题记录不存在")

    if e.source_type == "grammar":
        from app.models.grammar import GrammarExercise, GrammarPoint
        ex = db.query(GrammarExercise).filter(GrammarExercise.id == e.source_id).first()
        if not ex:
            raise HTTPException(404, "原语法题不存在")
        candidates = db.query(GrammarExercise).filter(
            GrammarExercise.grammar_point_id == ex.grammar_point_id,
            GrammarExercise.id != ex.id,
        ).order_by(random_order()).limit(req.count).all()
        if len(candidates) < req.count:
            extra = db.query(GrammarExercise).filter(
                GrammarExercise.id != ex.id,
                GrammarExercise.id.notin_([c.id for c in candidates]),
            ).order_by(random_order()).limit(req.count - len(candidates)).all()
            candidates = candidates + extra
        point = db.query(GrammarPoint).filter(GrammarPoint.id == ex.grammar_point_id).first()
        questions = [{
            "qid": c.id,
            "kind": "study",
            "question": c.question,
            "options": _parse_options(c.options),
            # 防刷：不下发正确答案，逐题判分走 /api/study/check-answer
            "explanation": c.explanation or "",
            "type_name": point.name if point else "语法练习",
        } for c in candidates]
        return {"kind": "study", "sub_kind": "grammar", "module_name": point.name if point else "语法练习",
                "count": len(questions), "questions": questions}

    if e.source_type == "classical":
        from app.models.classical import ClassicalText
        from app.routers.classical import _generate_quiz_from_text
        text = db.query(ClassicalText).filter(ClassicalText.id == e.source_id).first()
        if not text:
            raise HTTPException(404, "原篇目不存在")
        qs = _generate_quiz_from_text(text, req.count)
        questions = [{
            "qid": 0,
            "kind": "study",
            "question": q["question"],
            "options": [],
            "answer": q["answer"],
            "explanation": "",
            "type_name": "古诗文默写",
            "text_id": q["text_id"],
        } for q in qs]
        return {"kind": "study", "sub_kind": "classical", "module_name": f"《{text.title}》默写",
                "count": len(questions), "questions": questions}

    if e.source_type == "vocab":
        from app.models.word import Word
        orig = db.query(Word).filter(Word.id == e.source_id).first()
        if not orig:
            raise HTTPException(404, "原单词不存在")
        # 从同一词册取其他单词作为候选
        candidates = db.query(Word).filter(
            Word.book_id == orig.book_id,
            Word.id != orig.id,
        ).order_by(random_order()).limit(req.count).all()
        if len(candidates) < req.count:
            extra = db.query(Word).filter(
                Word.id != orig.id,
                Word.id.notin_([c.id for c in candidates]),
            ).order_by(random_order()).limit(req.count - len(candidates)).all()
            candidates = candidates + extra
        questions = [{
            "qid": c.id,
            "kind": "study",
            "question": f"✍️ 听写：{c.pos + ' ' if c.pos else ''}{c.meaning}",
            "options": [],
            "answer": c.word,
            "explanation": "",
            "type_name": "单词听写",
        } for c in candidates]
        return {"kind": "study", "sub_kind": "vocab", "module_name": "单词听写重练",
                "count": len(questions), "questions": questions}

    raise HTTPException(400, "未知的错题来源")


class CheckAnswerRequest(BaseModel):
    user_id: str
    kind: str  # exam / grammar
    qid: int
    user_answer: str


@router.post("/check-answer", summary="变式重练逐题判分（防刷：答案不下发前端）")
def check_answer_api(req: CheckAnswerRequest, db: Session = Depends(get_db)):
    """变式重练/错题修正的逐题判分：retry 接口不再下发正确答案，
    前端作答后调此接口由后端判对错，避免看答案抄写刷掌握。
    """
    if req.kind == "exam":
        q = db.query(Question).filter(Question.id == req.qid).first()
        if not q:
            raise HTTPException(404, "题目不存在")
        from app.routers.exam import _check_answer
        ok = _check_answer(req.user_answer or "", (q.answer or "").strip(), q.options_json)
    elif req.kind == "grammar":
        from app.models.grammar import GrammarExercise
        ex = db.query(GrammarExercise).filter(GrammarExercise.id == req.qid).first()
        if not ex:
            raise HTTPException(404, "题目不存在")
        ua = (req.user_answer or "").strip().lower()
        ca = (ex.answer or "").strip().lower()
        if ex.options:
            ok = ua == ca  # 选择题按字母判
        else:
            from app.services.answer_check import fill_answer_correct
            ok = ua == ca or fill_answer_correct(ua, ca)
    else:
        raise HTTPException(400, "kind 只能是 exam/grammar")
    return {"correct": bool(ok)}


def _parse_options(options_json: str) -> list:
    """解析选项 JSON 字符串，失败返回空列表"""
    if not options_json:
        return []
    try:
        data = json.loads(options_json)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


__all__ = ["RetryRequest", "retry_wrong", "CheckAnswerRequest", "check_answer_api", "_parse_options"]
