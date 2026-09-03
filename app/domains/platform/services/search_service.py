"""搜题服务层：题干规范化 + 本地题库相似匹配 + AI 讲解降级

处理流程（文字版，见 task-607 第 3 节）：
  孩子录入题干（可选学科）
    → 题干规范化（去空白 / 全半角 / 题号前缀）
    → 本地题库匹配（questions 小学 + middle_questions 初中六科）
        相似度：规范化后双向字符 bigram 重合率，阈值 >= 0.6 视为命中
    → 未命中 → AI 讲解（免费链，三段式【思路】【解答】【举一反三】≤500 字）
    → 成功解答写 ai_qa(q_type='search')，规范化题干作全局缓存 key

约束（延续既定决策）：
- AI 功能走钻石计费 + 限频（由路由层 rate_limit 控制）
- 命中缓存直接免费返回；仅 AI 实时解答走钻石扣费（扣费失败不阻断）
"""
import json
import logging
import re

from sqlalchemy.orm import Session

from app.models.ai_usage import AiQa
from app.models.exam import Question
from app.models.middle import MiddleQuestion
from ..services import ai as ai_svc

logger = logging.getLogger(__name__)

SEARCH_THRESHOLD = 0.6

# 小学两科（questions 表）与初中六科（middle_questions 表）
_PRIMARY_SUBJECTS = ("数学", "英语")
_MIDDLE_SUBJECTS = ("物理", "化学", "生物", "道德与法治", "历史", "地理")


def _full_to_half(ch: str) -> str:
    """全角字符转半角（空格 + FF01~FF5E 区间）"""
    cp = ord(ch)
    if cp == 0x3000:
        return " "
    if 0xFF01 <= cp <= 0xFF5E:
        return chr(cp - 0xFEE0)
    return ch


def normalize_question(q: str) -> str:
    """题干规范化：去首尾空白、全角转半角、去题号前缀（用于匹配与缓存 key）"""
    if not q:
        return ""
    s = "".join(_full_to_half(c) for c in q.strip())
    s = re.sub(r"\s+", "", s)                      # 去所有空白
    s = re.sub(r"^\(?\d+[).、]?", "", s)            # 去掉 "(1)" / "1." / "1、" 前缀
    s = re.sub(r"^（?[一二三四五六七八九十]+[)、]", "", s)  # 去掉 "（一）" / "一、" 前缀
    return s


def _bigrams(s: str) -> set:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a: str, b: str) -> float:
    """双向字符 bigram 重合率（overlap coefficient = 交集 / 较小集合大小）"""
    if not a or not b:
        return 0.0
    A, B = _bigrams(a), _bigrams(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return inter / min(len(A), len(B))


def _parse_options(raw: str) -> list:
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []


def match_library(db: Session, norm: str, subject: str = "") -> dict | None:
    """在 questions + middle_questions 中找最相似题目（相似度 >= 阈值）。

    返回命中题目信息 dict，或 None。subject 非空时按学科预过滤以减少扫描。
    """
    if not norm:
        return None
    candidates: list = []

    # 小学两科（questions 表）
    if not subject or subject in _PRIMARY_SUBJECTS:
        q_primary = db.query(Question)
        if subject in _PRIMARY_SUBJECTS:
            q_primary = q_primary.filter(Question.subject == subject)
        for q in q_primary.all():
            cand = normalize_question(q.question)
            if not cand:
                continue
            sc = similarity(norm, cand)
            if sc >= SEARCH_THRESHOLD:
                candidates.append((sc, "questions", q))

    # 初中六科（middle_questions 表）
    if not subject or subject in _MIDDLE_SUBJECTS:
        q_mid = db.query(MiddleQuestion)
        if subject in _MIDDLE_SUBJECTS:
            q_mid = q_mid.filter(MiddleQuestion.subject == subject)
        for q in q_mid.all():
            cand = normalize_question(q.question)
            if not cand:
                continue
            sc = similarity(norm, cand)
            if sc >= SEARCH_THRESHOLD:
                candidates.append((sc, "middle", q))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    sc, src, q = candidates[0]
    opts = _parse_options(getattr(q, "options_json", "") or "")
    return {
        "source": src,
        "question_id": q.id,
        "subject": getattr(q, "subject", ""),
        "question": q.question,
        "answer": getattr(q, "answer", "") or "",
        "analysis": getattr(q, "analysis", "") or "",
        "options": opts,
        "score": round(sc, 3),
    }


def cached_search(db: Session, norm: str) -> dict | None:
    """查 ai_qa(q_type='search') 全局缓存：相同规范化题干直接复用，不再请求 AI。"""
    row = db.query(AiQa).filter(
        AiQa.q_type == "search", AiQa.degraded == 0, AiQa.question == norm,
    ).order_by(AiQa.id.desc()).first()
    if row:
        return {"cached": True, "ai_text": row.answer, "provider": row.provider}
    return None


def ai_explain(user_id: str, norm: str, raw_question: str, grade: int = 0) -> dict | None:
    """未命中题库时调用 AI 生成三段式讲解；成功由路由层写入 ai_qa 缓存。

    返回 chat_for 的结果 dict（含 text/provider/...），或 None（AI 不可用）。
    """
    grade_label = f"{grade}年级" if grade and grade > 0 else "小学"
    system = (
        "你是中小学生的解题辅导老师，正在帮孩子解答一道题。"
        "要求：1) 语言口语化、鼓励，孩子一定能听懂，禁止生硬术语和批评；"
        "2) 只输出三段，分别用【思路】【解答】【举一反三】开头；"
        "3)【思路】先讲怎么想、从哪入手，不要直接给答案；"
        "4)【解答】给出完整过程与答案；理科分步骤，文科给要点；"
        "5)【举一反三】出 1 道同类型变式（只给题目，不给答案）；"
        "6) 全文不超过 500 字。"
    )
    user = f"孩子年级：{grade_label}\n题目：{raw_question}\n请按上面的要求讲解。"
    return ai_svc.chat_for(user_id, system, user, max_tokens=700)
