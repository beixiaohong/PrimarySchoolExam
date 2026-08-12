"""阅读理解专项服务层：按年级抽篇 + 交卷判分

判分规则：
- 客观选择题（type=choice）：服务端即时判分（支持选项字母 A-D 或选项文本匹配）
- 主观简答（type=short）：走 AI 判分（要点加权 ratio，0~1），降级为 0 分并回显参考答案
- 计费用钻石（按 AI 实际 token），失败不阻断
"""
import json
import logging

from sqlalchemy.orm import Session

from ..models.reading import ReadingPassage
from ..services import ai as ai_svc
from ..services.diamond import check_and_deduct

logger = logging.getLogger(__name__)


def get_passages(db: Session, subject: str, grade: int, limit: int = 5) -> list:
    """按学科+年级抽取阅读篇目（仅 approved 或 pending 均可抽，结构正确即可出题）"""
    rows = db.query(ReadingPassage).filter(
        ReadingPassage.subject == subject,
        ReadingPassage.grade == grade,
    ).order_by(ReadingPassage.id).limit(limit).all()
    out = []
    for p in rows:
        try:
            questions = json.loads(p.questions_json or "[]")
        except Exception:
            questions = []
        # 下发时隐藏答案与参考要点，避免泄露；保留题型/题干/选项供作答
        safe_q = []
        for i, q in enumerate(questions):
            safe_q.append({
                "qid": i,
                "type": q.get("type"),
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "score": q.get("score", 0),
            })
        out.append({
            "id": p.id,
            "subject": p.subject,
            "grade": p.grade,
            "semester": p.semester,
            "title": p.title,
            "passage": p.passage,
            "questions": safe_q,
            "review_status": p.review_status,
        })
    return out


def submit_reading_quiz(db: Session, user_id: str, passage_id: int,
                        answers: list) -> dict:
    """交卷判分：客观即时判、主观走 AI；返回逐题结果、总分、解析。

    answers: [{qid, user_answer}]；主观题 user_answer 为自由文本。
    """
    passage = db.query(ReadingPassage).filter(ReadingPassage.id == passage_id).first()
    if not passage:
        raise ValueError("阅读篇目不存在")
    try:
        questions = json.loads(passage.questions_json or "[]")
    except Exception:
        questions = []

    ans_map = {a.get("qid"): (a.get("user_answer") or "") for a in answers}
    total_score = 0.0
    max_score = 0.0
    detail = []
    ai_calls = 0

    for i, q in enumerate(questions):
        max_score += float(q.get("score", 0) or 0)
        ua = ans_map.get(i, "")
        if q.get("type") == "choice":
            ok, correct = _judge_choice(ua, q.get("answer", ""), q.get("options", []))
            earned = float(q.get("score", 0) or 0) if ok else 0.0
            detail.append({
                "qid": i, "type": "choice", "correct": bool(ok),
                "user_answer": ua, "correct_answer": correct,
                "earned": earned, "max": float(q.get("score", 0) or 0),
                "explanation": q.get("answer", ""),
            })
            total_score += earned
        else:
            # 主观简答 → AI 判分（要点 ratio）
            res = _grade_short(db, user_id, q, ua)
            ai_calls += 1
            detail.append({
                "qid": i, "type": "short", "correct": res["ratio"] >= 0.6,
                "user_answer": ua, "correct_answer": q.get("answer", ""),
                "earned": round(res["ratio"] * float(q.get("score", 0) or 0), 1),
                "max": float(q.get("score", 0) or 0),
                "comment": res["comment"], "degraded": res["degraded"],
                "explanation": q.get("answer", ""),
            })
            total_score += round(res["ratio"] * float(q.get("score", 0) or 0), 1)

    return {
        "passage_id": passage_id,
        "title": passage.title,
        "total_score": round(total_score, 1),
        "max_score": round(max_score, 1),
        "detail": detail,
    }


def _judge_choice(user_answer: str, correct_answer: str, options: list) -> (bool, str):
    """选择题判分：支持字母 A-D 或选项文本匹配"""
    ua = (user_answer or "").strip()
    ca = (correct_answer or "").strip()
    if not ua:
        return False, ca
    if len(ua) == 1 and ua.upper() in "ABCD":
        idx = "ABCD".index(ua.upper())
        if idx < len(options):
            return options[idx].strip() == ca, ca
    return ua.lower() == ca.lower(), ca


def _grade_short(db: Session, user_id: str, q: dict, user_answer: str) -> dict:
    """主观简答 AI 判分：返回 {ratio:0~1, comment, degraded}"""
    if not ai_svc.rate_limit(f"reading:{user_id}", 5, 60):
        return {"ratio": 0.0, "comment": "（判分过于频繁，请稍后再试）", "degraded": True}
    points = q.get("points", []) or []
    system = (
        "你是语文/英语阅读老师，负责对主观简答按要点给分。只输出 JSON，不要多余解释。"
        'JSON 结构：{"ratio": 0~1 的小数(相对满分的完成度), "comment": "一句话评语"}。'
        "ratio 参考：完整覆盖要点≈1，部分正确≈0.5，错误/未答≈0。"
    )
    user = (
        f"题目：{q.get('question', '')}\n参考答案要点：\n" +
        "\n".join(f"{k+1}. {pt}" for k, pt in enumerate(points)) +
        f"\n\n学生作答：\n{user_answer}"
    )
    result = ai_svc.chat_for(user_id, system, user, max_tokens=400)
    ratio = 0.0
    comment = ""
    degraded = False
    if result and result.get("text"):
        data = _extract_json(result["text"])
        if data and "ratio" in data:
            try:
                ratio = max(0.0, min(1.0, float(data["ratio"])))
            except Exception:
                ratio = 0.0
            comment = data.get("comment", "")
        else:
            degraded = True
            comment = "（AI 暂不可用，请对照参考答案）"
    else:
        degraded = True
        comment = "（AI 暂不可用，请对照参考答案）"

    if result and result.get("prompt_tokens") is not None:
        try:
            check_and_deduct(db, user_id, result["prompt_tokens"],
                             result.get("completion_tokens", 0), reason="阅读简答判分")
        except Exception:
            pass
    return {"ratio": ratio, "comment": comment, "degraded": degraded}


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
