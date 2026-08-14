"""AI 主观题判分路由：作文批改 + 阅读简答判分（钻石计费，限频）

- POST /api/ai/grade-essay      作文批改评分卡（分学段评分制，落库 essay_grades）
- POST /api/ai/grade-short-answer  阅读/简答要点判分（0/1/2 分档 + 评语）

AI 不可用时降级为本地模板，不阻断前端；计费失败不阻断（与全站一致）。
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.essay import EssayGrade
from ..services import ai as ai_svc
from ..services.diamond import check_and_deduct

logger = logging.getLogger(__name__)
router = APIRouter()

# 分学段满分（D5 决议）：语文 小学30/初中50，英语 小学15/初中20
MAX_SCORE = {
    ("语文", "小学"): 30, ("语文", "初中"): 50,
    ("英语", "小学"): 15, ("英语", "初中"): 20,
}


class EssayGradeRequest(BaseModel):
    user_id: str
    subject: str = "语文"        # 语文/英语
    grade: int = 6               # 决定学段满分
    topic: str = ""
    content: str = ""           # ≤800 字


class ShortAnswerGradeRequest(BaseModel):
    user_id: str
    question: str = ""
    reference_points: list = []  # 参考答案要点（字符串列表）
    user_answer: str = ""


def _extract_json(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                return None
    return None


def _stage(grade: int) -> str:
    return "小学" if grade <= 6 else "初中"


def _essay_system(subject: str, stage: str, max_score: int) -> str:
    return (
        f"你是一位耐心的小学/初中{subject}老师，负责作文批改。请按{stage}评分标准，"
        f"满分 {max_score} 分。只输出 JSON，不要多余解释。JSON 结构："
        f'{{"total": 数字(0~{max_score}), '
        f'"dims": {{"内容": 数字, "结构": 数字, "语言": 数字, "卷面": 数字}}, '
        f'"highlights": ["亮点1", "亮点2"], '
        f'"improvements": ["改进建议1", "改进建议2"], '
        f'"upgraded": "一段升格示例(50字内)"}}。'
        f"四维分项之和应接近 total。先肯定优点，再给可操作建议，语气鼓励、符合{stage}生口吻。"
    )


def _essay_user(topic: str, content: str) -> str:
    return f"题目：{topic or '（自拟）'}\n作文：\n{content}"


@router.post("/grade-essay", summary="作文批改评分卡（分学段，落库可回看）")
def grade_essay(req: EssayGradeRequest):
    if req.subject not in ("语文", "英语"):
        raise HTTPException(400, "subject 仅支持 语文/英语")
    if len(req.content) > 800:
        raise HTTPException(400, "作文字数超过 800 字上限")
    if not ai_svc.rate_limit(f"essay:{req.user_id}", 3, 60):
        raise HTTPException(429, "作文批改过于频繁，请稍后再试（限 3 次/分）")

    stage = _stage(req.grade)
    max_score = MAX_SCORE[(req.subject, stage)]
    card = None
    degraded = False
    # AI 调用在会话外执行，不占数据库连接
    result = ai_svc.chat_for(req.user_id, _essay_system(req.subject, stage, max_score),
                             _essay_user(req.topic, req.content), max_tokens=800)
    if result and result.get("text"):
        card = _extract_json(result["text"])
    if not card or "total" not in card:
        degraded = True
        card = {
            "total": 0, "max": max_score,
            "dims": {"内容": 0, "结构": 0, "语言": 0, "卷面": 0},
            "highlights": ["（AI 暂不可用，请稍后再试）"],
            "improvements": ["（AI 暂不可用，请稍后再试）"],
            "upgraded": "",
        }
    # 归一化字段，避免前端取值为空
    card.setdefault("max", max_score)
    card.setdefault("dims", {"内容": 0, "结构": 0, "语言": 0, "卷面": 0})
    card.setdefault("highlights", [])
    card.setdefault("improvements", [])
    card.setdefault("upgraded", "")

    # 落库 / 计费：短会话
    db = SessionLocal()
    try:
        rec = EssayGrade(user_id=req.user_id, subject=req.subject, grade=req.grade,
                         topic=req.topic, content=req.content, score_json=json.dumps(card, ensure_ascii=False))
        db.add(rec)
        db.commit()
        db.refresh(rec)

        # 钻石计费（按 AI 实际用量；失败不阻断）
        if result and result.get("prompt_tokens") is not None:
            try:
                check_and_deduct(db, req.user_id, result["prompt_tokens"],
                                 result.get("completion_tokens", 0), reason="作文批改")
            except Exception:
                pass
    finally:
        db.close()

    return {"id": rec.id, "subject": req.subject, "stage": stage,
            "max_score": max_score, "card": card, "degraded": degraded}


@router.post("/grade-short-answer", summary="阅读/简答要点判分（0/1/2 分档 + 评语）")
def grade_short_answer(req: ShortAnswerGradeRequest):
    if not ai_svc.rate_limit(f"short:{req.user_id}", 5, 60):
        raise HTTPException(429, "简答判分过于频繁，请稍后再试（限 5 次/分）")
    points = req.reference_points or []
    max_score = 2 * len(points) if points else 0

    system = (
        "你是语文/英语阅读老师，负责按要点给主观简答判分。只输出 JSON，不要多余解释。"
        'JSON 结构：{"points": [{"point": "要点原文", "score": 0/1/2, "comment": "一句话评语"}], '
        '"total": 数字, "comment": "总体评语"}。score 取值 0(未答/错误)/1(部分正确)/2(完整正确)；'
        "total 为各要点 score 之和。"
    )
    user = (
        f"题目：{req.question}\n参考答案要点：\n" +
        "\n".join(f"{i+1}. {p}" for i, p in enumerate(points)) +
        f"\n\n学生作答：\n{req.user_answer}"
    )

    data = None
    degraded = False
    # AI 调用在会话外执行，不占数据库连接
    result = ai_svc.chat_for(req.user_id, system, user, max_tokens=600)
    if result and result.get("text"):
        data = _extract_json(result["text"])
    if not data or "points" not in data:
        degraded = True
        data = {
            "points": [{"point": p, "score": 0, "comment": "（AI 暂不可用，请稍后复核）"} for p in points],
            "total": 0, "comment": "（AI 暂不可用，请稍后复核）",
        }
    data.setdefault("total", sum(p.get("score", 0) for p in data.get("points", [])))
    data.setdefault("comment", "")

    # 钻石计费：短会话（失败不阻断）
    if result and result.get("prompt_tokens") is not None:
        db = SessionLocal()
        try:
            try:
                check_and_deduct(db, req.user_id, result["prompt_tokens"],
                                 result.get("completion_tokens", 0), reason="简答判分")
            except Exception:
                pass
        finally:
            db.close()

    return {"max_score": max_score, "total": data["total"],
            "points": data["points"], "comment": data["comment"], "degraded": degraded}
