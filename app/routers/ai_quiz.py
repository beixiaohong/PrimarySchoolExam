"""AI 趣味出题（AI-2 增强创意 24）：AI 生成趣味包装的题目 + 作答闭环

孩子选学科/趣味主题（冒险/太空/恐龙/美食/魔法），AI 生成 5 道趣味题，
前端在线作答判分；答错的题回写 study_errors 进入错题闭环。
全对奖励金币 +5（与金币宠物联动）。
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .pet import _grant_coins

router = APIRouter(tags=["AI 趣味出题"])

THEMES = {
    "adventure": "冒险岛探险",
    "space": "太空旅行",
    "dino": "恐龙世界",
    "food": "美食厨房",
    "magic": "魔法学院",
}

QUIZ_PAID = 5  # 全对奖励金币

SYSTEM_PROMPT = """你是一位小学 AI 出题老师。根据要求生成趣味题目，要求：
1. 题目必须符合对应年级和学科的难度，是真实可解的题；
2. 把题目包装成 {theme} 主题的趣味场景，让孩子觉得好玩；
3. 每题给出 4 个选项（A/B/C/D）方便孩子选择，也可以出填空题（options 为 null）；
4. 每道题附一段「趣味小知识」（fun），与主题相关，让孩子涨知识；
5. 难度循序渐进，前易后难。

只输出一个 JSON 对象，格式严格如下（不要输出任何其他文字）：
{{"questions": [{{"question": "题目文字", "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"] | null, "answer": "正确选项字母或填空答案", "explanation": "解析", "fun": "趣味小知识"}}]}}"""


class QuizGenReq(BaseModel):
    user_id: str
    subject: str = "数学"  # 数学/语文/英语
    grade: int = 6
    theme: str = "adventure"
    count: int = 5


class QuizWrongReq(BaseModel):
    user_id: str
    question: str
    user_answer: str = ""
    correct_answer: str
    explanation: str = ""


class QuizRewardReq(BaseModel):
    user_id: str
    correct: int
    total: int


@router.post("/generate", summary="AI 生成趣味题（主题包装）")
def generate_quiz(req: QuizGenReq, db: Session = Depends(get_db)):
    from ..services.ai import chat_with

    if req.subject not in ("数学", "语文", "英语"):
        raise HTTPException(400, "学科只能是 数学/语文/英语")
    theme = THEMES.get(req.theme)
    if not theme:
        raise HTTPException(400, f"主题可选：{', '.join(THEMES.keys())}")

    user_prompt = (
        f"请为{req.grade}年级孩子生成 {req.count} 道{req.subject}趣味题，"
        f"主题是「{theme}」。题目要生动有趣，贴近孩子生活。"
    )
    text = ""
    for attempt in range(2):
        resp = chat_with(req.user_id, SYSTEM_PROMPT, user_prompt, max_tokens=1600)
        text = (resp or {}).get("text", "") or ""
        questions = _parse_questions(text)
        if questions:
            # 钻石扣费
            try:
                from ..services import diamond as diamond_svc
                diamond_svc.check_and_deduct(db, req.user_id,
                                              (resp or {}).get("prompt_tokens", 0),
                                              (resp or {}).get("completion_tokens", 0),
                                              reason="ai_quiz")
            except Exception:
                pass
            return {"theme": theme, "count": len(questions), "questions": questions,
                    "raw": None}
    raise HTTPException(502, "AI 生成失败了，稍后再试一次吧")


def _parse_questions(text: str) -> list:
    """从 AI 回复中提取题目 JSON 数组（容错：找 { 到 } 之间的 JSON）"""
    if not text:
        return []
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    qs = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(qs, list):
        return []
    out = []
    for q in qs[:8]:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        options = q.get("options") or None
        if isinstance(options, list):
            options = [str(o) for o in options][:4]
        out.append({
            "question": str(q["question"]).strip(),
            "options": options,
            "answer": str(q.get("answer", "")).strip(),
            "explanation": str(q.get("explanation", "")).strip(),
            "fun": str(q.get("fun", "")).strip(),
        })
    return out


@router.post("/wrong", summary="AI 趣味题答错 → 回写错题本")
def submit_wrong(req: QuizWrongReq, db: Session = Depends(get_db)):
    from ..models.study_error import StudyError

    if not req.question.strip() or not req.correct_answer.strip():
        raise HTTPException(400, "题目内容缺失")
    # 同题不重复入库（来源 ai_quiz）
    existing = db.query(StudyError).filter(
        StudyError.user_id == req.user_id,
        StudyError.source_type == "ai_quiz",
        StudyError.question == req.question.strip(),
    ).first()
    if existing:
        existing.is_mastered = False
        existing.mastered_at = None
        existing.correct_streak = 0
        existing.error_count += 1
        existing.user_answer = req.user_answer
        existing.correct_answer = req.correct_answer
        existing.explanation = req.explanation
    else:
        db.add(StudyError(
            user_id=req.user_id, source_type="ai_quiz", source_id=0,
            module_name="AI 趣味出题", question=req.question.strip(),
            user_answer=req.user_answer, correct_answer=req.correct_answer,
            explanation=req.explanation, error_count=1,
        ))
    db.commit()
    return {"ok": True}


@router.post("/reward", summary="AI 趣味题全对 +5 金币")
def quiz_reward(req: QuizRewardReq, db: Session = Depends(get_db)):
    if req.total <= 0 or req.correct < req.total:
        return {"ok": True, "granted": 0}
    _grant_coins(db, req.user_id, QUIZ_PAID, "趣味出题全对")
    db.commit()
    return {"ok": True, "granted": QUIZ_PAID}
