"""搜题智能解答 API（文字版，拍照搜题依 D2 决议延期至下期）

接口：
- POST /api/search/ask      录入题干 → 题库命中 或 AI 讲解（缓存/计费/错题本联动）
- POST /api/search/to-wrong 把搜到的题写入错题本（去重：同题干不重复入库）
- GET  /api/search/history  本人搜题历史（ai_qa q_type=search 倒序，前 50 条）

限频：ask 5 次/分钟/用户（复用 ai_svc.rate_limit）。
计费（D1 决议）：命中缓存 / 题库命中 直接免费；仅 AI 实时解答走钻石扣费（扣费失败不阻断）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.ai_usage import AiQa
from app.models.study_error import StudyError
from ..services import ai as ai_svc
from ..services.search_service import (
    ai_explain, cached_search, match_library, normalize_question,
)

logger = logging.getLogger(__name__)

router = APIRouter()

SEARCH_RATE = 5       # 搜题限频：次/分钟/用户
SEARCH_MAX_LEN = 500  # 题干最长字符数


# ── 请求体 ──
class SearchAskReq(BaseModel):
    user_id: str
    question_text: str
    subject: str = ""      # 可选学科（数学/英语/物理/...）
    grade: int = 0         # 可选年级（用于 AI 讲解口吻）
    force_ai: bool = False  # 强制走 AI 讲解（跳过题库命中，供「AI 讲解」按钮）


class SearchToWrongReq(BaseModel):
    user_id: str
    question: str
    answer: str = ""
    explanation: str = ""


# ── 用量与扣费（与 routers/ai.py 一致） ──
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


def _deduct_diamonds(db: Session, user_id: str, result: dict, feature: str) -> dict:
    """根据 AI 返回的 token 用量扣除钻石，返回扣费信息（失败不阻断主流程）"""
    try:
        from app.domains.commerce.contracts import DiamondService
        info = DiamondService.consume(
            db, user_id,
            result.get("prompt_tokens", 0), result.get("completion_tokens", 0),
            biz=f"ai_{feature}",
        )
        return info
    except Exception as e:
        logger.warning("钻石扣费失败: %s", e)
        return {"ok": True, "cost": 0, "balance": 0, "error": ""}


def _balance(db: Session, user_id: str) -> float:
    from app.domains.commerce.contracts import DiamondService
    try:
        return DiamondService.balance(db, user_id)
    except Exception:
        return 0.0


def _empty_payload(text: str, user_id: str, subject: str, db: Session) -> dict:
    return {
        "hit": False, "cached": False,
        "question": text, "question_id": None, "source": None,
        "subject": subject, "answer": "", "analysis": "", "options": [],
        "score": 0,
        "ai_text": "AI 老师暂时有点忙，稍后再试一下吧！可以先把已知条件列一列～",
        "diamond_cost": 0, "diamond_balance": _balance(db, user_id),
    }


@router.post("/ask", summary="文字搜题：题库命中 或 AI 讲解（缓存/计费/错题本联动）")
def search_ask(req: SearchAskReq):
    """文字搜题：优先命中本地题库，其次命中全局缓存，最后走 AI 实时讲解。

    参数（Body）：user_id、question_text（<=500 字）、subject、grade、force_ai（跳过题库命中）。
    返回：{hit, cached, question, question_id, source, subject, answer, analysis, options,
          score, ai_text, diamond_cost, diamond_balance}。题库命中/缓存免费，仅 AI 实时解答扣钻石。
    限频：SEARCH_RATE=5 次/分钟/用户。副作用：成功解答写 ai_qa(q_type=search) 并扣钻石。
    无需家长密码。
    """
    text = (req.question_text or "").strip()
    if not text:
        raise HTTPException(400, "题目不能为空")
    if len(text) > SEARCH_MAX_LEN:
        raise HTTPException(400, f"题目太长啦，{SEARCH_MAX_LEN} 字以内")
    if not ai_svc.rate_limit(f"search:{req.user_id}", SEARCH_RATE, 60):
        raise HTTPException(400, "搜题太快啦，休息一下再来吧")

    norm = normalize_question(text)

    # 1) 题库 / 缓存命中：短会话，取完即释放，等待 AI 期间不占连接池
    db = SessionLocal()
    try:
        if not req.force_ai:
            hit = match_library(db, norm, req.subject or "")
            if hit:
                return {
                    "hit": True, "cached": False,
                    "question": hit["question"], "question_id": hit["question_id"],
                    "source": hit["source"], "subject": hit["subject"],
                    "answer": hit["answer"], "analysis": hit["analysis"],
                    "options": hit["options"], "score": hit["score"],
                    "ai_text": None,
                    "diamond_cost": 0, "diamond_balance": _balance(db, req.user_id),
                }

        # 2) 缓存命中（之前 AI 解答过相同规范化题干，任意用户）
        cached = cached_search(db, norm)
        if cached:
            return {
                "hit": False, "cached": True,
                "question": text, "question_id": None, "source": None,
                "subject": req.subject or "", "answer": "", "analysis": "", "options": [],
                "score": 0,
                "ai_text": cached["ai_text"],
                "diamond_cost": 0, "diamond_balance": _balance(db, req.user_id),
            }
    finally:
        db.close()

    # 3) AI 实时解答（会话外执行，不占数据库连接）
    result = ai_explain(req.user_id, norm, text, req.grade or 0)

    # 4) 写回 / 计费：短会话
    db = SessionLocal()
    try:
        if result and result["text"].strip():
            db.add(AiQa(
                user_id=req.user_id, question=norm, answer=result["text"],
                provider=result.get("provider") or "", model=result.get("model") or "",
                q_type="search", degraded=0,
            ))
            try:
                db.commit()
            except Exception as e:
                logger.warning("写 ai_qa(search) 失败: %s", e)
                db.rollback()
            _log_usage(db, req.user_id, "search_ask", True, result)
            diamond_info = _deduct_diamonds(db, req.user_id, result, "search")
            return {
                "hit": False, "cached": False,
                "question": text, "question_id": None, "source": None,
                "subject": req.subject or "", "answer": "", "analysis": "", "options": [],
                "score": 0,
                "ai_text": result["text"],
                "diamond_cost": diamond_info.get("cost", 0),
                "diamond_balance": diamond_info.get("balance", 0),
            }

        # 降级：AI 不可用（不写库，避免缓存劣质答案）
        _log_usage(db, req.user_id, "search_ask", False, error="AI 不可用，降级模板")
        return _empty_payload(text, req.user_id, req.subject or "", db)
    finally:
        db.close()


@router.post("/to-wrong", summary="把搜到的题加入错题本（去重：同题干不重复入库）")
def search_to_wrong(req: SearchToWrongReq, db: Session = Depends(get_db)):
    """把搜到的题写入错题本（按 用户+来源+题干 去重，同题干不重复入库）。

    参数（Body）：user_id、question、answer、explanation。
    返回：{ok, added, id, message}；已存在则 added=False。
    副作用：可能新建 study_errors 记录（source_type=search）。无需家长密码。
    """
    text = (req.question or "").strip()
    if not text:
        raise HTTPException(400, "题目不能为空")

    # 去重：同用户同题干不重复入库
    existing = db.query(StudyError).filter(
        StudyError.user_id == req.user_id,
        StudyError.source_type == "search",
        StudyError.question == text,
    ).first()
    if existing:
        return {"ok": True, "added": False, "id": existing.id, "message": "已在错题本中"}

    # source_id 用题干稳定哈希，满足 (user_id, source_type, source_id) 唯一约束
    source_id = abs(hash(text)) % (2 ** 31)
    err = StudyError(
        user_id=req.user_id,
        source_type="search",
        source_id=source_id,
        module_name="搜题",
        question=text,
        user_answer="",
        correct_answer=(req.answer or "")[:2000],
        explanation=(req.explanation or "")[:2000],
    )
    db.add(err)
    db.commit()
    db.refresh(err)
    return {"ok": True, "added": True, "id": err.id, "message": "已加入错题本"}


@router.get("/history", summary="我的搜题历史（前 50 条）")
def search_history(user_id: str = Query(..., min_length=1),
                   db: Session = Depends(get_db)):
    """返回本人搜题历史（ai_qa q_type=search 倒序，前 50 条）。

    参数（Query）：user_id。
    返回：[{id, question, answer, provider, model, created_at}]。
    副作用：无（只读）。无需家长密码。
    """
    rows = db.query(AiQa).filter(
        AiQa.user_id == user_id, AiQa.q_type == "search",
    ).order_by(AiQa.id.desc()).limit(50).all()
    return [{
        "id": r.id, "question": r.question, "answer": r.answer,
        "provider": r.provider, "model": r.model,
        "created_at": str(r.created_at)[:16],
    } for r in rows]
