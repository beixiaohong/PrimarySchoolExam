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

from app.database import SessionLocal, get_db
from app.domains.family.contracts import MIDDLE_SUBJECTS
from app.domains.engagement.contracts import _grant_coins

router = APIRouter(tags=["AI 趣味出题"])

THEMES = {
    "adventure": "冒险岛探险",
    "space": "太空旅行",
    "dino": "恐龙世界",
    "food": "美食厨房",
    "magic": "魔法学院",
}

# 支持的学科：小学语数英 + 初中六科（初中学科用 middle 题库同款趣味包装生成）
QUIZ_SUBJECTS = ["数学", "语文", "英语"] + MIDDLE_SUBJECTS

QUIZ_PAID = 5  # 全对奖励金币

# 学科→难度锚点（用于年级感知的 prompt 措辞，避免初中题出成小学难度）
_SUBJECT_STAGE = {
    "数学": "小学", "语文": "小学", "英语": "小学",
    "物理": "初中", "化学": "初中", "生物": "初中",
    "道德与法治": "初中", "历史": "初中", "地理": "初中",
}

SYSTEM_PROMPT = """你是一位{stage} AI 出题老师。根据要求生成趣味题目，要求：
1. 题目必须符合对应年级和学科（{stage}）的难度，是真实可解的题，不要超纲；
2. 把题目包装成 {theme} 主题的趣味场景，让孩子觉得好玩；
3. 每题给出 4 个选项（A/B/C/D）方便孩子选择，也可以出填空题（options 为 null）；
4. 每道题附一段「趣味小知识」（fun），与主题相关，让孩子涨知识；
5. 难度循序渐进，前易后难。

只输出一个 JSON 对象，格式严格如下（不要输出任何其他文字）：
{{"questions": [{{"question": "题目文字", "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"] | null, "answer": "正确选项字母或填空答案", "explanation": "解析", "fun": "趣味小知识"}}]}}"""


class QuizGenReq(BaseModel):
    user_id: str
    subject: str = "数学"  # 数学/语文/英语 + 初中六科（物理/化学/生物/道德与法治/历史/地理）
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
def generate_quiz(req: QuizGenReq):
    """AI 生成趣味题（主题包装）。

    请求：{user_id, subject=数学/语文/英语, grade, theme, count}；无需家长密码。
    返回：{theme, count, questions:[{question,options,answer,explanation,fun}]}（questions 为空时抛 502）。
    副作用：最多重试 2 次解析 AI 输出；成功按 token 扣钻（reason=ai_quiz），扣费失败不阻断。
    """
    from app.domains.platform.contracts import chat_with

    if req.subject not in QUIZ_SUBJECTS:
        raise HTTPException(400, f"学科只能是 {('/'.join(QUIZ_SUBJECTS))}")
    theme = THEMES.get(req.theme)
    if not theme:
        raise HTTPException(400, f"主题可选：{', '.join(THEMES.keys())}")

    stage = _SUBJECT_STAGE.get(req.subject, "小学")
    system_prompt = SYSTEM_PROMPT.format(stage=stage, theme=theme)
    user_prompt = (
        f"请为{req.grade}年级（{stage}）孩子生成 {req.count} 道{req.subject}趣味题，"
        f"主题是「{theme}」。题目要生动有趣，贴近该年级孩子的生活与认知水平。"
    )
    text = ""
    # AI 调用在会话外执行（可能重试 2 次），不占数据库连接
    for attempt in range(2):
        resp = chat_with(req.user_id, system_prompt, user_prompt, max_tokens=1600)
        text = (resp or {}).get("text", "") or ""
        questions = _parse_questions(text)
        if questions:
            # 钻石扣费：短会话
            try:
                from app.domains.commerce.contracts import diamond as diamond_svc
                db = SessionLocal()
                try:
                    diamond_svc.check_and_deduct(db, req.user_id,
                                                  (resp or {}).get("prompt_tokens", 0),
                                                  (resp or {}).get("completion_tokens", 0),
                                                  reason="ai_quiz")
                finally:
                    db.close()
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
    """AI 趣味题答错 → 回写错题本（错题闭环）。

    请求：{user_id, question, user_answer, correct_answer, explanation}；无需家长密码。
    返回：{ok}。
    副作用：写 study_errors（source_type=ai_quiz）；同题（同用户+同内容）不重复入库，
            已存在则重置掌握状态、error_count+1，便于后续重练。
    """
    from app.models.study_error import StudyError

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
    """AI 趣味题全对奖励金币（+5，与金币宠物联动）。

    请求：{user_id, correct, total}；无需家长密码。
    返回：{ok, granted}（granted=0 表示未全对，不发放）。
    副作用：仅当 correct==total 且 total>0 时调用 _grant_coins(+5, reason=趣味出题全对) 并落库。
    """
    if req.total <= 0 or req.correct < req.total:
        return {"ok": True, "granted": 0}
    _grant_coins(db, req.user_id, QUIZ_PAID, "趣味出题全对")
    db.commit()
    return {"ok": True, "granted": QUIZ_PAID}
