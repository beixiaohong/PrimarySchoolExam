"""采集式题库的刷题抽题服务

从 paper_questions（采集试卷解析出的单题）按「年级 + 学科 + 题型」随机抽题，
供后续「刷题系统」使用。与原有 questions/exam_records（出题式题库）完全解耦。

设计要点：
- grade / subject / qtype 三个维度从 PaperQuestion 自身冗余列筛选，不依赖 JOIN papers。
- 随机排序使用 database.random_order()（已统一为 MySQL 的 rand()）。
- 只负责「抽题 + 统计」，判分逻辑复用 routers.exam._check_answer（保持去重/容错判题一致）。
"""
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import random_order
from app.models.paper import PaperQuestion


def random_paper_questions(
    db: Session,
    grade: Optional[str] = None,
    subject: Optional[str] = None,
    qtype: Optional[str] = None,
    limit: int = 10,
    exclude_ids: Optional[List[int]] = None,
) -> List[PaperQuestion]:
    """从采集题库随机抽题。

    参数：
      grade:   年级字符串，如 "一年级" / "初三" / "中考"
      subject: 学科字符串，如 "数学" / "语文"
      qtype:   题型 choice / fill_blank / qa
      limit:   抽取数量（内部裁剪到 1~50）
      exclude_ids: 排除的题目 id 列表（避免一次练习重复出题）
    返回：PaperQuestion 列表（已随机排序）。
    """
    limit = max(1, min(int(limit), 50))
    q = db.query(PaperQuestion)
    if grade:
        q = q.filter(PaperQuestion.grade == grade)
    if subject:
        q = q.filter(PaperQuestion.subject == subject)
    if qtype:
        q = q.filter(PaperQuestion.qtype == qtype)
    if exclude_ids:
        q = q.filter(PaperQuestion.id.notin_(exclude_ids))
    return q.order_by(random_order()).limit(limit).all()


def get_paper_questions_by_ids(db: Session, ids: List[int]) -> Dict[int, PaperQuestion]:
    """按 id 批量取题，返回 {id: PaperQuestion}，供提交判分时回查标准答案。"""
    if not ids:
        return {}
    rows = db.query(PaperQuestion).filter(PaperQuestion.id.in_(ids)).all()
    return {r.id: r for r in rows}


def count_paper_questions(
    db: Session,
    grade: Optional[str] = None,
    subject: Optional[str] = None,
    qtype: Optional[str] = None,
) -> int:
    """统计采集题库（按筛选条件）的题目数量，用于前端展示题库规模。"""
    q = db.query(func.count(PaperQuestion.id))
    if grade:
        q = q.filter(PaperQuestion.grade == grade)
    if subject:
        q = q.filter(PaperQuestion.subject == subject)
    if qtype:
        q = q.filter(PaperQuestion.qtype == qtype)
    return int(q.scalar() or 0)


def collection_stats(db: Session) -> dict:
    """采集题库规模统计：总量 + 各学科/年级分布，便于前端展示与 M7 验证。"""
    total = count_paper_questions(db)
    by_subject = {}
    rows = db.query(PaperQuestion.subject, func.count(PaperQuestion.id)).group_by(
        PaperQuestion.subject
    ).all()
    for subj, cnt in rows:
        by_subject[subj or "(未标注)"] = int(cnt)
    by_grade = {}
    rows = db.query(PaperQuestion.grade, func.count(PaperQuestion.id)).group_by(
        PaperQuestion.grade
    ).all()
    for g, cnt in rows:
        by_grade[g or "(未标注)"] = int(cnt)
    return {"total": total, "by_subject": by_subject, "by_grade": by_grade}


# ═══════════════ 刷题组合：题库 + AI 自适应 ═══════════════

def _parse_ai_questions(text: str) -> list:
    """从 AI 回复中容错解析题目 JSON（复用 ai_quiz 的解析思路）。"""
    import json as _json, re as _re
    if not text:
        return []
    m = _re.search(r"\{.*\}", text, _re.S)
    if not m:
        return []
    try:
        data = _json.loads(m.group(0))
    except Exception:
        return []
    qs = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(qs, list):
        return []
    out = []
    for q in qs[:12]:
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
        })
    return out


def ai_generate_questions(subject: str, grade: int = 7, count: int = 5,
                          topic: str = None) -> list:
    """AI 实时生成题目（刷题题库不足时补足）。

    遵守连接池铁律：AI 调用在 db 会话外执行，不占连接。
    返回 [{question, options, answer, explanation}]，失败返回 []。
    """
    from app.domains.platform.services.ai import chat_with
    stage = "初中" if str(subject) in ("物理", "化学", "生物", "道德与法治", "历史", "地理") else "小学"
    try:
        if int(grade) >= 7:
            stage = "初中"
    except Exception:
        pass
    focus = f"，重点考查：{topic}" if topic else ""
    system = (
        "你是一位{stage}出题老师。请生成真实可解、不超纲的{subject}练习题，"
        "每题给出 4 个选项（A/B/C/D）或填空题（options 为 null），并附解析。"
        "只输出一个 JSON 对象："
        "{{\"questions\":[{{\"question\":\"题目\",\"options\":[\"A.xxx\",\"B.xxx\",\"C.xxx\",\"D.xxx\"]|null,"
        "\"answer\":\"正确选项或填空答案\",\"explanation\":\"解析\"}}]}}"
    ).format(stage=stage, subject=subject)
    user = f"为{grade}年级学生生成 {count} 道{subject}练习题{focus}，难度循序渐进，前易后难。"
    for _ in range(2):
        try:
            resp = chat_with("system", system, user, max_tokens=1600)
        except Exception:
            return []
        text = (resp or {}).get("text", "") or ""
        qs = _parse_ai_questions(text)
        if qs:
            return qs
    return []


def mixed_practice(
    db: Session,
    grade: Optional[str] = None,
    subject: Optional[str] = None,
    qtype: Optional[str] = None,
    limit: int = 10,
    ai_fill: bool = True,
    topic: Optional[str] = None,
) -> List[dict]:
    """组合刷题：优先从采集题库抽题，不足部分用 AI 生成补足（自适应）。

    返回统一结构（含 source 字段标记 bank/ai），兼容 /collection/practice 输出。
    AI 题以负 id 标记（id<=0 表示 AI 生成、不查库、判分时用携带答案）。
    """
    import json as _json
    limit = max(1, min(int(limit), 50))
    bank = random_paper_questions(db, grade=grade, subject=subject, qtype=qtype, limit=limit)
    out = []
    for q in bank:
        opts = []
        if q.options:
            try:
                opts = _json.loads(q.options)
            except Exception:
                opts = []
        out.append({
            "id": q.id, "source": "bank",
            "paper_id": q.paper_id, "seq": q.seq,
            "grade": q.grade or "", "subject": q.subject or "",
            "qtype": q.qtype or "", "section": q.section or "",
            "question_text": q.question_text or "",
            "question_html": q.question_html or "",
            "options": opts, "correct_answer": q.correct_answer or "",
            "explanation": q.explanation or "", "image_base64": q.image_base64 or "",
        })
    need = limit - len(out)
    if ai_fill and need > 0 and subject:
        try:
            g = int(grade) if str(grade).isdigit() else 7
        except Exception:
            g = 7
        ai_qs = ai_generate_questions(subject, g, need, topic=topic)
        for i, a in enumerate(ai_qs):
            opts = a["options"]
            out.append({
                "id": -1000 - i, "source": "ai",
                "paper_id": None, "seq": None,
                "grade": grade or "", "subject": subject or "",
                "qtype": "choice" if opts else "fill_blank",
                "section": "",
                "question_text": a["question"],
                "question_html": a["question"],
                "options": opts,
                "correct_answer": a["answer"],
                "explanation": a["explanation"], "image_base64": "",
            })
    return out
