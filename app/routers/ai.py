"""AI API：错题讲解 / 成长周报 / 即时鼓励语

约定：
- 全部调用走 app.services.ai（多提供商：智谱 GLM 免费（glm-4.7-flash，失败自动回退 glm-4.7 标准版）/ DeepSeek 付费，VIP 用户可享付费链）
- 未配置 Key 或全链调用失败 → degraded=true + 本地模板，前端无感
- 每次调用记录 ai_usage_log（provider/用量/失败原因）
"""
import json
import logging
import random
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog
from ..models.daily_task import DailyTask
from ..services import ai as ai_svc

logger = logging.getLogger(__name__)

router = APIRouter()

CAUSE_CN = {
    "careless": "粗心看错",
    "concept": "概念没弄懂",
    "method": "方法不会",
    "reading": "审题失误",
    "ai": "孩子点 AI 讲解标记的（未自评）",
    "": "还没有自评错因",
}

EXPLAIN_CACHE: dict = {}  # (user, question_id) -> (ts, text)
CACHE_TTL = 24 * 3600

# ── 降级模板 ──
ENCOURAGE_TEMPLATES = {
    "combo_broken": [
        "差一点点！下次连击会更猛 🔥",
        "断了也没关系，重新来过更有挑战！",
        "哦豁！试试深呼吸，下一题赢回来 💪",
    ],
    "wrong_answer": [
        "错了也没关系，看看解析就明白啦！",
        "每一次错题都是进步的机会 ✨",
        "没关系，订正一次就多掌握一个知识点！",
    ],
    "perfect": [
        "全对！太厉害了 🎉",
        "完美！今天的你状态爆棚 ✨",
        "全对通关，继续保持！",
    ],
    "default": [
        "加油！每天进步一点点 ✨",
        "坚持就是胜利，你已经很棒了！",
        "继续冲！你的努力都看得见 💪",
    ],
}


class ExplainReq(BaseModel):
    user_id: str
    question_id: int


class ExplainMarkReq(BaseModel):
    user_id: str
    question_id: int


class ReportReq(BaseModel):
    user_id: str


class EncourageReq(BaseModel):
    user_id: str
    context: str = "default"


def _log_usage(db: Session, user_id: str, feature: str, ok: bool,
               result: dict | None = None, error: str = ""):
    from ..models.ai_usage import AIUsageLog  # noqa: 延迟导入避免循环
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
        from ..services import diamond as diamond_svc
        prompt_tokens = result.get("prompt_tokens", 0)
        completion_tokens = result.get("completion_tokens", 0)
        info = diamond_svc.check_and_deduct(db, user_id, prompt_tokens, completion_tokens,
                                            reason=f"ai_{feature}")
        return info
    except Exception as e:
        logger.warning("钻石扣费失败: %s", e)
        return {"ok": True, "cost": 0, "balance": 0, "error": ""}


# ═══════════════════ 1. AI 错题讲解 ═══════════════════

def _explain_core(db: Session, user_id: str, q: Question, wrong: WrongRecord) -> dict:
    """讲解核心：24h 内存缓存 → 数据库全局缓存（同题复用，不再请求 AI）→ AI 调用 → 降级模板。

    返回体不含 marked。所有成功讲解写入 ai_qa（q_type=explain），
    十万个为什么历史页可回看，相同题目（任意用户）直接复用答案。
    """
    key = (user_id, q.id)
    cached = EXPLAIN_CACHE.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return {"degraded": False, "cached": True, "text": cached[1],
                "question": q.question, "answer": q.answer}

    # 数据库全局缓存：同题（ref_id）已有成功讲解 → 直接复用，不再请求 AI
    from ..models.ai_usage import AiQa
    db_cached = db.query(AiQa).filter(
        AiQa.q_type == "explain", AiQa.ref_id == q.id, AiQa.degraded == 0,
    ).order_by(AiQa.id.desc()).first()
    if db_cached:
        EXPLAIN_CACHE[key] = (time.time(), db_cached.answer)
        return {"degraded": False, "cached": True, "text": db_cached.answer,
                "question": q.question, "answer": q.answer}

    cause_text = CAUSE_CN.get(wrong.cause, CAUSE_CN[""])
    subject = q.subject
    system = (
        "你是小学辅导老师，正在给孩子讲解一道做错的题。"
        "要求：1) 语言口语化、鼓励，孩子（6年级）一定能懂，禁止批评和生硬术语；"
        "2) 只输出三段，用【错在哪】【怎么做】【再来一道】三个小标题开头；"
        "3)【怎么做】分步骤讲，不超过5步；"
        f"4)【再来一道】出 1 道同类型变式题（只给题目，不给答案）；"
        f"5) 全文不超过 350 字。"
    )
    user = (
        f"学科：{subject}\n"
        f"孩子自己认为的错因：{cause_text}\n"
        f"题目：{q.question}\n"
        f"参考答案：{q.answer}\n"
        "请按上面的要求给孩子讲解。"
    )
    result = ai_svc.chat_for(user_id, system, user, max_tokens=900)
    if result and result["text"].strip():
        EXPLAIN_CACHE[key] = (time.time(), result["text"])
        db.add(AiQa(user_id=user_id, question=q.question, answer=result["text"],
                    provider=result.get("provider") or "",
                    model=result.get("model") or "",
                    q_type="explain", ref_id=q.id, degraded=0))
        try:
            db.commit()
        except Exception as e:
            logger.warning("写 ai_qa（讲解）失败: %s", e)
            db.rollback()
        _log_usage(db, user_id, "explain", True, result)
        diamond_info = _deduct_diamonds(db, user_id, result, "explain")
        return {"degraded": False, "cached": False, "text": result["text"],
                "question": q.question, "answer": q.answer,
                "diamond_cost": diamond_info.get("cost", 0),
                "diamond_balance": diamond_info.get("balance", 0)}
    # 降级：本地解析（不写库，避免缓存劣质答案）
    _log_usage(db, user_id, "explain", False, error="AI 不可用，降级模板")
    fallback = (
        f"【错在哪】{cause_text}，这道题你选了/写了和答案不一样的内容。\n"
        f"【怎么做】先认真读题，把条件和问题圈出来；按题目类型用学过的步骤一步步算；做完后把答案代回去检查一遍。\n"
        f"【再来一道】订正完这道题，去刷题中心找同类型的题目再做 2 题巩固一下吧！"
    )
    return {"degraded": True, "cached": False, "text": fallback,
            "question": q.question, "answer": q.answer}


@router.post("/explain", summary="错题 AI 讲解（三段式 + 变式题）")
def ai_explain(req: ExplainReq, db: Session = Depends(get_db)):
    # 限频：5 次/分钟/用户
    if not ai_svc.rate_limit(f"explain:{req.user_id}", 5, 60):
        raise HTTPException(400, "讲解太快啦，休息一下再来吧")

    wrong = db.query(WrongRecord).filter_by(
        user_id=req.user_id, question_id=req.question_id).first()
    if not wrong:
        raise HTTPException(404, "这道题不在错题本里")
    q = db.query(Question).filter_by(id=req.question_id).first()
    if not q:
        raise HTTPException(404, "题目不存在")
    return _explain_core(db, req.user_id, q, wrong)


@router.post("/explain-mark", summary="标记错题（AI 讲解）并生成讲解")
def ai_explain_mark(req: ExplainMarkReq, db: Session = Depends(get_db)):
    """作答页「AI 讲解」按钮：一键把题目标记为做错了（错因=ai）并弹讲解。

    - 题目不在错题本 → 自动创建错题记录（错因标注 ai，展示为「AI 讲解」）
    - 已在错题本且未自评错因 → 补标 ai；已自评过 → 保留用户自评
    - 返回体在讲解基础上附加 marked（本次是否新标记）与 record_id（错题记录，供变式重练）
    """
    if not ai_svc.rate_limit(f"explain:{req.user_id}", 5, 60):
        raise HTTPException(400, "讲解太快啦，休息一下再来吧")

    q = db.query(Question).filter_by(id=req.question_id).first()
    if not q:
        raise HTTPException(404, "题目不存在")
    wrong = db.query(WrongRecord).filter_by(
        user_id=req.user_id, question_id=req.question_id).first()
    marked = False
    if not wrong:
        wrong = WrongRecord(user_id=req.user_id, question_id=req.question_id,
                            cause="ai", wrong_at=datetime.now())
        db.add(wrong)
        db.commit()
        db.refresh(wrong)
        marked = True
    elif not wrong.cause:
        wrong.cause = "ai"
        db.commit()
        marked = True

    out = _explain_core(db, req.user_id, q, wrong)
    out["marked"] = marked
    out["record_id"] = wrong.id
    return out


# ═══════════════════ 2. AI 成长周报 ═══════════════════

def _week_range() -> tuple[date, date]:
    """上周一 ~ 上周日"""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(days=7), monday - timedelta(days=1)


def _aggregate_week(db: Session, user_id: str) -> dict:
    start, end = _week_range()
    start_dt, end_dt = datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.max.time())
    stats = {
        "week_start": str(start), "week_end": str(end),
        "attempts": 0, "avg_score": 0, "wrong_mastered": 0,
        "new_words": 0, "classical_learned": 0, "full_days": 0,
        "best_mood_day": None, "ai_explains": 0,
    }
    # 本周心情最好的一天（mood 档位：great > happy > ok > blue > sad，取最好的一天）
    from ..models.mood import MoodCheckin
    moods = db.query(MoodCheckin).filter(
        MoodCheckin.user_id == user_id,
        MoodCheckin.check_date >= start, MoodCheckin.check_date <= end,
    ).order_by(MoodCheckin.check_date.asc()).all()
    if moods:
        order = {"great": 0, "happy": 1, "ok": 2, "blue": 3, "sad": 4}
        best = min(moods, key=lambda r: order.get(r.mood, 9))
        stats["best_mood_day"] = {
            "date": str(best.check_date),
            "mood": best.mood,
            "label": {"great": "超开心", "happy": "开心", "ok": "一般", "blue": "有点烦", "sad": "很难过"}.get(best.mood, best.mood),
        }
    # 本周 AI 讲解使用次数（周报亮点数据源，q_type=explain 非降级记录）
    from ..models.ai_usage import AiQa
    stats["ai_explains"] = db.query(AiQa).filter(
        AiQa.user_id == user_id,
        AiQa.q_type == "explain",
        AiQa.degraded == 0,
        AiQa.created_at >= start_dt, AiQa.created_at <= end_dt,
    ).count()
    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.user_id == user_id,
        ExamAttempt.created_at >= start_dt, ExamAttempt.created_at <= end_dt,
    ).all()
    stats["attempts"] = len(attempts)
    if attempts:
        stats["avg_score"] = round(sum(a.score or 0 for a in attempts) / len(attempts))
    stats["wrong_mastered"] = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
        WrongRecord.is_mastered == True,  # noqa: E712
        WrongRecord.mastered_at >= start_dt, WrongRecord.mastered_at <= end_dt,
    ).count()
    rows = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.learn_date >= start, VocabDailyLog.learn_date <= end,
    ).all()
    stats["new_words"] = sum(r.new_words_learned or 0 for r in rows)
    rows = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.learn_date >= start, ClassicalDailyLog.learn_date <= end,
    ).all()
    stats["classical_learned"] = sum((r.texts_learned or 0) + (r.texts_reviewed or 0) for r in rows)
    # 全勤天数：三科任务全部 done 的天数
    for d in (start + timedelta(days=i) for i in range(7)):
        done = db.query(DailyTask).filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date == d, DailyTask.status == "done",
        ).count()
        if done >= 3:
            stats["full_days"] += 1
    return stats


@router.post("/report", summary="生成/获取上周成长周报（幂等）")
def ai_report(req: ReportReq, db: Session = Depends(get_db)):
    if not ai_svc.rate_limit(f"report:{req.user_id}", 2, 86400):
        raise HTTPException(400, "今天周报已生成过啦")

    from ..models.ai_usage import WeeklyReport
    stats = _aggregate_week(db, req.user_id)
    week_start = stats["week_start"]
    existing = db.query(WeeklyReport).filter_by(
        user_id=req.user_id, week_start=date.fromisoformat(week_start)).first()
    if existing:
        try:
            cached = json.loads(existing.content_json or "{}")
        except (ValueError, TypeError):
            cached = {}
        cached["already_exists"] = True
        return cached

    # 亮点候选（真实数据）
    highlights = []
    if stats["wrong_mastered"]:
        highlights.append(f"本周消灭了 {stats['wrong_mastered']} 道错题")
    if stats["new_words"]:
        highlights.append(f"新学了 {stats['new_words']} 个单词")
    if stats["classical_learned"]:
        highlights.append(f"背诵默写了 {stats['classical_learned']} 篇古诗文")
    if stats["attempts"]:
        highlights.append(f"完成了 {stats['attempts']} 套练习，平均正确率 {stats['avg_score']}%")
    if stats["full_days"]:
        highlights.append(f"三科全勤 {stats['full_days']} 天")
    if stats.get("best_mood_day"):
        highlights.append(f"本周心情最好的一天是 {stats['best_mood_day']['date'][5:]}（{stats['best_mood_day']['label']}）")
    if stats.get("ai_explains"):
        highlights.append(f"AI 讲解用了 {stats['ai_explains']} 次，好学好问")
    if not highlights:
        highlights.append("上周是休息周，本周一起加油")

    # AI 润色 + 下周建议
    advice = "保持每天完成三科任务，错题当天订正效果最好！"
    degraded = True
    result = ai_svc.chat_for(
        req.user_id,
        "你是小学学习系统的成长教练，为家长写周报建议。语气温暖，只鼓励不批评，只输出 1 句 20 字以内的建议。",
        f"孩子上周表现：{'；'.join(highlights)}。请给孩子写一句下周建议。",
        max_tokens=100,
    )
    if result and result["text"].strip():
        advice = result["text"][:60]
        degraded = False
        _log_usage(db, req.user_id, "report", True, result)
        _deduct_diamonds(db, req.user_id, result, "report")
    else:
        _log_usage(db, req.user_id, "report", False, error="AI 不可用，降级模板")

    # 家长寄语：取最近一条周报（可能是占位行）
    latest = db.query(WeeklyReport).filter(
        WeeklyReport.user_id == req.user_id,
    ).order_by(WeeklyReport.week_start.desc()).first()
    parent_note = getattr(latest, "parent_note", "") if latest else ""

    payload = {
        "week_start": week_start,
        "week_end": stats["week_end"],
        "highlights": highlights,
        "advice": advice,
        "degraded": degraded,
        "parent_note": parent_note,
        "stats": {k: v for k, v in stats.items() if k not in ("week_start", "week_end")},
    }
    db.add(WeeklyReport(user_id=req.user_id, week_start=date.fromisoformat(week_start),
                        content_json=json.dumps(payload, ensure_ascii=False),
                        status="done"))
    db.commit()
    return payload


# ═══════════════════ 3. AI 即时鼓励语 ═══════════════════

@router.post("/encourage", summary="一句 AI 鼓励语（≤20 字）")
def ai_encourage(req: EncourageReq, db: Session = Depends(get_db)):
    if not ai_svc.rate_limit(f"encourage:{req.user_id}", 3, 60):
        return {"text": random.choice(ENCOURAGE_TEMPLATES["default"]), "degraded": True}
    ctx_map = {"combo_broken": "孩子连续答对后中断了连击", "wrong_answer": "孩子刚答错一题",
               "perfect": "孩子这次全对", "default": "孩子正在学习中"}
    result = ai_svc.chat_for(
        req.user_id,
        "你是小学学习系统的鼓励小助手。只输出 1 句不超过 20 个字的鼓励语，语气温暖有趣，适合 6 年级孩子。",
        ctx_map.get(req.context, ctx_map["default"]) + "，请说一句鼓励的话。",
        max_tokens=60,
    )
    if result:
        text = result["text"].strip().strip('"').strip("「」")[:40]
        if text:
            _log_usage(db, req.user_id, "encourage", True, result)
            _deduct_diamonds(db, req.user_id, result, "encourage")
            return {"text": text, "degraded": False}
    _log_usage(db, req.user_id, "encourage", False, error="AI 不可用，降级模板")
    return {"text": random.choice(ENCOURAGE_TEMPLATES.get(req.context, ENCOURAGE_TEMPLATES["default"])),
            "degraded": True}
