"""AI 学习助手（AI-5）：基于孩子真实学习数据（画像）的多轮对话助手

- GET /api/assistant/profile：孩子的学习画像（今日任务、错题、最近考试、金币/树/徽章等），
  供 AI 上下文使用，前端也可展示
- POST /api/assistant/chat：多轮对话，携带最近 6 轮历史 + 学习画像 → AI 给出
  个性化学习建议 / 错题讲解 / 鼓励（默认免费链 zhipu → relay）
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from ..services import ai as ai_svc

logger = logging.getLogger(__name__)

router = APIRouter()

ASSIST_MAX_LEN = 300
ASSIST_RATE = 5
SESSION_ROUNDS = 6

SYSTEM_PROMPT = (
    "你是小学生的「AI 学习助手」，会结合孩子的真实学习数据给出建议。要求：\n"
    "1) 语言口语化、温暖、鼓励式，孩子（{grade} 年级）一定能听懂，禁止生硬术语；\n"
    "2) 结合【孩子的学习画像】回答，用具体数字表扬进步（比如「昨天做对了 X 道题」），不要凭空夸；\n"
    "3) 给建议时一次最多 2 条，具体可执行（如「今晚先复习错题本里的 2 道计算题」）；\n"
    "4) 全文不超过 250 字；\n"
    "5) 这是多轮对话，如果孩子追问，请结合前面聊过的内容继续回答，不要重复已说过的内容。\n\n"
    "【孩子的学习画像】\n{profile}"
)


class ChatReq(BaseModel):
    user_id: str
    message: str
    history: list = []  # [{"role": "me"|"ai", "content": "..."}, ...] 最近几轮


class ChatTurn(BaseModel):
    role: str
    content: str


def _log_usage(db: Session, user_id: str, feature: str, ok: bool,
               result: dict | None = None, error: str = ""):
    from app.models.ai_usage import AIUsageLog
    try:
        db.add(AIUsageLog(
            user_id=user_id,
            provider=(result or {}).get("provider") or "template",
            feature=feature,
            model=(result or {}).get("model") or "",
            prompt_tokens=(result or {}).get("prompt_tokens") or 0,
            completion_tokens=(result or {}).get("completion_tokens") or 0,
            ok=ok,
            error=error[:500],
        ))
        db.commit()
    except Exception as e:  # 用量记录失败不影响主流程
        logger.warning("写 AI 用量日志失败: %s", e)
        db.rollback()


def _build_profile(db: Session, user_id: str, grade: int, subject: str) -> str:
    """汇总孩子学习数据为紧凑画像文本"""
    from datetime import date, timedelta
    from sqlalchemy import func

    from app.models.study_error import StudyError
    from app.models.exam import ExamAttempt
    from app.models.daily_task import DailyTask
    from app.models.badge import BadgeEarned
    from app.domains.engagement.routers.pet import _balance
    from app.domains.engagement.routers.tree import compute_tree_score

    lines = []
    # 今日任务
    try:
        tasks = db.query(DailyTask).filter(DailyTask.user_id == user_id,
                                           DailyTask.task_date == date.today()).all()
        done = sum(1 for t in tasks if getattr(t, "status", "") == "done")
        lines.append(f"今日任务：完成 {done}/{len(tasks)}")
    except Exception:
        pass
    # 错题
    try:
        wrong_rows = db.query(StudyError).filter(
            StudyError.user_id == user_id,
            StudyError.is_mastered == 0,
        ).order_by(StudyError.error_count.desc()).limit(5).all()
        if wrong_rows:
            parts = []
            for w in wrong_rows:
                q = (w.question or "")[:36]
                parts.append(f"{w.module_name}:{q}(答{w.user_answer}，正{w.correct_answer})")
            lines.append("待攻克错题" + str(len(wrong_rows)) + "道：" + "；".join(parts))
        else:
            lines.append("错题本已清空，好棒！")
    except Exception:
        pass
    # 最近考试
    try:
        exams = db.query(ExamAttempt).filter(
            ExamAttempt.user_id == user_id,
        ).order_by(ExamAttempt.id.desc()).limit(3).all()
        if exams:
            parts = [f"{e.subject} {e.score}/100" for e in exams]
            lines.append("最近考试：" + "、".join(parts))
    except Exception:
        pass
    # 徽章/树/金币
    try:
        badge_count = db.query(func.count(BadgeEarned.id)).filter(
            BadgeEarned.user_id == user_id).scalar() or 0
        tree_score = compute_tree_score(db, user_id)
        balance = _balance(db, user_id)
        lines.append(f"已获得 {badge_count} 枚徽章；成长树 {tree_score} 分；金币余额 {balance}")
    except Exception:
        pass
    # 连续打卡（daily_tasks 往前数）
    try:
        from app.models.daily_task import DailyTask as DT
        d = date.today()
        streak = 0
        for i in range(60):
            day = d - timedelta(days=i)
            rows = db.query(DT).filter(DT.user_id == user_id, DT.task_date == day).all()
            if rows and all(getattr(t, "status", "") == "done" for t in rows):
                streak += 1
            else:
                break
        if streak:
            lines.append(f"已连续 {streak} 天完成任务")
    except Exception:
        pass
    return "；".join(lines) if lines else "暂无学习数据（新用户）"


@router.get("/profile", summary="孩子学习画像（AI 学习助手用）")
def assistant_profile(user_id: str = Query(...), db: Session = Depends(get_db)):
    """孩子学习画像（供 AI 学习助手上下文，前端也可展示）。

    查询参数：user_id；无需家长密码。
    返回：{grade, subject, profile}（profile 为今日任务/错题/最近考试/徽章/树/金币/连续打卡的文本摘要）。
    副作用：只读，无写库。
    """
    from app.models.user import User

    u = db.query(User).filter(User.user_id == user_id).first()
    grade = u.grade if u else 6
    subject = u.subject if u else "数学"
    return {
        "grade": grade,
        "subject": subject,
        "profile": _build_profile(db, user_id, grade, subject),
    }


@router.post("/chat", summary="AI 学习助手多轮对话（结合学习画像）")
def assistant_chat(req: ChatReq):
    """AI 学习助手多轮对话（结合学习画像）。

    请求：{user_id, message, history(最近几轮)}；无需家长密码。
    返回：{text, model, provider}（无有效回复抛 502）。
    副作用：限频 5 次/分钟，消息限 300 字；组装最近 6 轮历史 + 实时学习画像调用 AI，
            成功按 token 扣钻（reason=ai_assistant）并写 ai_usage_log，扣费失败不阻断。
    """
    from app.models.user import User

    message = (req.message or "").strip()
    if not message:
        raise HTTPException(400, "说点什么吧～")
    if len(message) > ASSIST_MAX_LEN:
        raise HTTPException(400, f"问题太长啦，{ASSIST_MAX_LEN} 字以内")
    if not ai_svc.rate_limit(f"assistant:{req.user_id}", ASSIST_RATE, 60):
        raise HTTPException(400, "提问太快啦，休息一下再来吧")

    # 读阶段短会话：画像组装完即释放，等待 AI 期间不占连接池
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.user_id == req.user_id).first()
        grade = u.grade if u else 6
        subject = u.subject if u else "数学"
        profile = _build_profile(db, req.user_id, grade, subject)
    finally:
        db.close()
    system = SYSTEM_PROMPT.format(grade=grade, profile=profile)

    # 组装历史（最近 N 轮，role 转 ai/assistant 兼容）
    history = []
    for t in (req.history or [])[-SESSION_ROUNDS:]:
        role = "assistant" if str(t.get("role", "")).lower() in ("ai", "assistant") else "user"
        content = str(t.get("content", ""))[:400]
        if content:
            history.append({"role": role, "content": content})

    user_prompt = f"孩子的问题是：{message}\n（孩子当前默认学科：{subject}）"
    # AI 调用在会话外执行，不占数据库连接
    resp = ai_svc.chat_with(req.user_id, system, user_prompt, max_tokens=700)

    # 日志 / 扣费：短会话
    db = SessionLocal()
    try:
        if not resp or not resp.get("text"):
            _log_usage(db, req.user_id, "assistant", False, resp, "AI 无有效回复")
            raise HTTPException(502, "AI 老师正在打盹，稍后再试试吧")
        _log_usage(db, req.user_id, "assistant", True, resp)
        # 钻石扣费
        try:
            from app.services import diamond as diamond_svc
            diamond_svc.check_and_deduct(db, req.user_id,
                                          resp.get("prompt_tokens", 0),
                                          resp.get("completion_tokens", 0),
                                          reason="ai_assistant")
        except Exception:
            pass
    finally:
        db.close()
    return {"text": resp["text"].strip(), "model": resp.get("model", ""),
            "provider": resp.get("provider", "")}
