"""AI 十万个为什么：提问 → 全局缓存命中 / 指定模型 AI 回答 → 入库；历史问答列表

约定：
- 模型选择：zhipu（智谱，付费优先自动降级）/ relay（GPT 中转站）/ deepseek（仅 VIP）
- 相同问题（规范化文本）全局共享答案：命中直接返回 cached=true，不再请求 AI
- 所有成功问答写入 ai_qa 表（q_type=qa），题目讲解（q_type=explain）由 routers/ai.py 写入
- 降级模板不写库、不参与缓存命中
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.ai_usage import AiQa
from ..services import ai as ai_svc

logger = logging.getLogger(__name__)

router = APIRouter()

QA_MAX_LEN = 300  # 问题最长字符数
QA_RATE = 5       # 提问限频：次/分钟/用户

SYSTEM_PROMPT = (
    "你是小学生「十万个为什么」的讲解老师。"
    "要求：1) 语言口语化、生动有趣，孩子（6 年级）一定能听懂，禁止生硬术语；"
    "2) 先一句话直接回答，再用 2-3 个小点简单解释原因；"
    "3) 全文不超过 250 字；"
    "4) 只回答孩子的提问，不要说题外话。"
)

PROVIDER_LABELS = {
    "zhipu": "智谱 GLM",
    "relay": "GPT",
    "deepseek": "DeepSeek",
}


class AskReq(BaseModel):
    user_id: str
    question: str
    provider: str = "zhipu"  # zhipu / relay / deepseek


def _norm_question(q: str) -> str:
    """规范化问题文本：去空白（用于全局缓存匹配）"""
    return re.sub(r"\s+", "", q.strip())


def _log_usage(db: Session, user_id: str, feature: str, ok: bool,
               result: dict | None = None, error: str = ""):
    from ..models.ai_usage import AIUsageLog
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


@router.get("/models", summary="可选 AI 模型列表（含 VIP 状态与可用性）")
def qa_models(user_id: str = Query(..., min_length=1)):
    is_vip = ai_svc._is_vip(user_id)
    models = []
    for key in ("zhipu", "relay", "deepseek"):
        cfg = ai_svc._config_provider(key)
        available = bool(cfg["api_key"])
        if key == "deepseek":
            available = available and is_vip
        models.append({
            "key": key,
            "label": PROVIDER_LABELS.get(key, key),
            "model": cfg["model"],
            "vip_only": key in ai_svc.PAID_CHAIN,
            "available": available,
        })
    return {"vip": is_vip, "models": models}


@router.post("/ask", summary="十万个为什么提问（全局缓存命中则秒回）")
def qa_ask(req: AskReq, db: Session = Depends(get_db)):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    if len(question) > QA_MAX_LEN:
        raise HTTPException(400, f"问题太长啦，{QA_MAX_LEN} 字以内")
    provider = req.provider or "zhipu"
    if provider not in ai_svc.PROVIDERS:
        raise HTTPException(400, "不支持的 AI 模型")
    # DeepSeek 仅 VIP（服务层也拦截，这里给出友好提示）
    if provider in ai_svc.PAID_CHAIN and not ai_svc._is_vip(req.user_id):
        raise HTTPException(403, "DeepSeek 仅 VIP 用户可用，找家长开通哦")
    if not ai_svc.rate_limit(f"qa:{req.user_id}", QA_RATE, 60):
        raise HTTPException(400, "提问太快啦，休息一下再来吧")

    # 1) 全局缓存命中：相同问题直接展示已有回答（不再次请求 AI）
    norm = _norm_question(question)
    cached = db.query(AiQa).filter(
        AiQa.q_type == "qa", AiQa.degraded == 0,
        AiQa.question == norm,
    ).order_by(AiQa.id.desc()).first()
    if cached:
        return {
            "cached": True,
            "answer": cached.answer,
            "provider": cached.provider,
            "model": cached.model,
            "question": question,
        }

    # 2) 未命中 → 指定模型 AI 调用
    result = ai_svc.chat_with(req.user_id, SYSTEM_PROMPT, question,
                              max_tokens=500, provider=provider)
    if result and result["text"].strip():
        db.add(AiQa(user_id=req.user_id, question=norm, answer=result["text"],
                    provider=result.get("provider") or provider,
                    model=result.get("model") or "",
                    q_type="qa", degraded=0))
        try:
            db.commit()
        except Exception as e:
            logger.warning("写 ai_qa 失败: %s", e)
            db.rollback()
        _log_usage(db, req.user_id, "qa_ask", True, result)
        return {
            "cached": False,
            "answer": result["text"],
            "provider": result.get("provider") or provider,
            "model": result.get("model") or "",
            "question": question,
        }

    # 3) AI 不可用 → 降级（不写库，避免缓存劣质答案）
    _log_usage(db, req.user_id, "qa_ask", False, error=f"AI 不可用（{provider}）")
    return {
        "cached": False, "degraded": True,
        "answer": "AI 老师暂时有点忙，换个问题或稍后再试一下吧！",
        "provider": "", "model": "", "question": question,
    }


@router.get("/history", summary="我的问答历史（十万个为什么 + 题目讲解）")
def qa_history(user_id: str = Query(..., min_length=1),
               q_type: str = Query("all", pattern="^(all|qa|explain)$"),
               db: Session = Depends(get_db)):
    q = db.query(AiQa).filter(AiQa.user_id == user_id)
    if q_type != "all":
        q = q.filter(AiQa.q_type == q_type)
    rows = q.order_by(AiQa.id.desc()).limit(100).all()
    return [{
        "id": r.id, "question": r.question, "answer": r.answer,
        "provider": r.provider, "model": r.model, "q_type": r.q_type,
        "ref_id": r.ref_id, "created_at": str(r.created_at)[:16],
    } for r in rows]
