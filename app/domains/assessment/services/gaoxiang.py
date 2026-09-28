"""软考高项备考服务层（assessment 域）

职责分界：
- 本文件：静态考纲数据、AI 输出解析（纯函数，可单测）、判分/错题回写/进度聚合（DB 逻辑）。
- routers/gaoxiang.py：HTTP 编排。**AI 调用发生在 DB 会话之外**（铁律：不得持连接等
  外部阻塞调用），调用成功后才开短会话落库/扣费。

设计要点：
- 题目落库复用：AI 生成的题存入 gx_questions，刷题时优先从「该用户未做过」的
  题库出题，不够才补生成 —— 同样的内容不重复扣费。
- 错题闭环与小学侧同构：答错进错题本，重做连对 3 次自动掌握。
- 判分在服务端做（与 ai_quiz 的前端判分不同）：答案存库，防止前端被绕过刷进度。
"""
import json
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.gaoxiang import GxKnowledge, GxQuestion, GxAttempt, GxWrong, GxProgress

logger = logging.getLogger("gaoxiang")

# ── 静态考纲：十大知识域（信息系统项目管理师第 4 版教材体系）──
GX_DOMAINS = [
    "整体管理", "范围管理", "进度管理", "成本管理", "质量管理",
    "资源管理", "沟通管理", "风险管理", "采购管理", "干系人管理",
]

# 题型
QTYPE_SINGLE = "single"
QTYPE_MULTI = "multi"
QTYPE_CASE = "case"
QTYPES = (QTYPE_SINGLE, QTYPE_MULTI, QTYPE_CASE)

# 重做连对 N 次自动掌握（与小学错题闭环一致）
MASTER_STREAK = 3

# 各题型 AI 单次生成的题数（太大易超时/超 token）
GEN_BATCH = {QTYPE_SINGLE: 5, QTYPE_MULTI: 4, QTYPE_CASE: 1}

QUIZ_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）的资深辅导老师，熟悉第4版教材与历年真题风格。
根据知识域与题型出题，要求：
1. 题目贴近真题风格：单选考概念辨析/ITO 归属/计算题，多选考过程/输入输出的组合；
2. 每题必须给出正确答案与一段简洁解析（说明为什么选它、易混淆点在哪）；
3. 严格按给定知识域出题，不要跨域；
4. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"questions": [{{"question": "题干", "options": ["A. ...", "B. ...", "C. ...", "D. ..."] 或 null(多选给4-5个), "answer": "正确选项字母（多选如 ABD）", "analysis": "解析"}}]}}"""

CASE_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）案例分析题的资深辅导老师。
按给定知识域出一道案例分析大题，要求：
1. 给出一段真实项目背景（200-400字，包含该知识域的典型问题情境）；
2. 出 2-3 个子问题，覆盖「找问题/说原因/给对策」中的至少两类；
3. 每个子问题给出参考答案要点（用于后续 AI 批改的评分依据）；
4. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"background": "背景材料", "sub_questions": [{{"q": "子问题", "answer": "参考答案要点", "points": 10}}]}}"""

KNOWLEDGE_SYSTEM_PROMPT = """你是软考高级「信息系统项目管理师」（高项）的资深辅导老师，熟悉第4版教材。
按给定知识域生成一批核心知识点卡片，要求：
1. 覆盖该知识域的主要考点：定义、主要过程、输入输出工具技术（ITO）、常考易混点；
2. 每个知识点 content 用简洁的结构化文字（可用换行与序号），200-400字；
3. 只输出一个 JSON 对象，不要输出任何其他文字：
{{"points": [{{"code": "如 4.1", "title": "知识点标题", "summary": "一句话摘要", "content": "正文"}}]}}"""


# ── AI 输出解析（纯函数） ──

def _extract_json(text: str):
    """从 AI 输出中提取首个 JSON 对象（容忍 markdown 代码围栏与前后杂文）"""
    if not text:
        return None
    text = text.strip()
    # 优先剥 ```json ... ``` 围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except Exception:
        pass
    # 兜底：取第一个 { 到最后一个 } 之间
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def parse_questions(text: str):
    """解析出题 AI 输出 → [{question, options, answer, analysis}]（结构非法的字段丢弃）"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return []
    out = []
    for q in data.get("questions") or []:
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        answer = (q.get("answer") or "").strip()
        if not question or not answer:
            continue
        options = q.get("options")
        if options is not None and not (isinstance(options, list) and options):
            options = None
        out.append({"question": question, "options": options,
                    "answer": answer, "analysis": (q.get("analysis") or "").strip()})
    return out


def parse_case(text: str):
    """解析案例出题 AI 输出 → {background, sub_questions:[{q, answer, points}]} 或 None"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    background = (data.get("background") or "").strip()
    subs = []
    for s in data.get("sub_questions") or []:
        if not isinstance(s, dict):
            continue
        q = (s.get("q") or "").strip()
        if not q:
            continue
        try:
            points = int(s.get("points") or 10)
        except (TypeError, ValueError):
            points = 10
        subs.append({"q": q, "answer": (s.get("answer") or "").strip(), "points": points})
    if not background or not subs:
        return None
    return {"background": background, "sub_questions": subs}


def parse_knowledge(text: str):
    """解析知识点 AI 输出 → [{code, title, summary, content}]"""
    data = _extract_json(text)
    if not isinstance(data, dict):
        return []
    out = []
    for p in data.get("points") or []:
        if not isinstance(p, dict):
            continue
        title = (p.get("title") or "").strip()
        content = (p.get("content") or "").strip()
        if not title or not content:
            continue
        out.append({"code": (p.get("code") or "").strip(), "title": title,
                    "summary": (p.get("summary") or "").strip()[:500], "content": content})
    return out


# ── 判分（纯函数） ──

def normalize_letters(s: str) -> str:
    """把答案归一为大写字母升序串（'b,a' / 'B A' → 'AB'），供单/多选比对"""
    return "".join(sorted({c for c in (s or "").upper() if "A" <= c <= "Z"}))


def grade_choice(user_answer: str, correct: str, qtype: str) -> bool:
    """单选/多选判分：字母归一后全等（多选必须全对，与考试规则一致）"""
    if qtype not in (QTYPE_SINGLE, QTYPE_MULTI):
        return False
    return bool(normalize_letters(user_answer)) and \
        normalize_letters(user_answer) == normalize_letters(correct)


# ── DB 逻辑（调用方持有会话，方法内不开新会话） ──

def _bump_progress(db: Session, user_id: str, domain: str, **inc) -> None:
    """进度增量更新（user_id+domain 一行，缺则建）"""
    row = db.query(GxProgress).filter_by(user_id=user_id, domain=domain).first()
    if row is None:
        row = GxProgress(user_id=user_id, domain=domain, knowledge_read=0,
                         quiz_total=0, quiz_correct=0, case_count=0)
        db.add(row)
    for k, v in inc.items():
        setattr(row, k, (getattr(row, k) or 0) + v)
    row.last_at = datetime.now()


def record_choice_attempt(db: Session, user_id: str, question: GxQuestion,
                          user_answer: str, duration_ms: int = 0) -> dict:
    """选择题作答：落记录 + 进度 + 错题闭环，返回 {is_correct, correct, analysis}

    错误：错题本 upsert（wrong_count+1、correct_streak 清零）；
    正确：若在错题本中则 correct_streak+1，达 MASTER_STREAK 自动掌握。
    """
    is_correct = grade_choice(user_answer, question.answer or "", question.qtype)
    db.add(GxAttempt(user_id=user_id, question_id=question.id,
                     user_answer=user_answer, is_correct=is_correct,
                     duration_ms=max(0, int(duration_ms or 0))))
    _bump_progress(db, user_id, question.domain,
                   quiz_total=1, quiz_correct=1 if is_correct else 0)

    wrong = db.query(GxWrong).filter_by(user_id=user_id, question_id=question.id).first()
    if is_correct:
        if wrong is not None and not wrong.is_mastered:
            wrong.correct_streak = (wrong.correct_streak or 0) + 1
            if wrong.correct_streak >= MASTER_STREAK:
                wrong.is_mastered = True
                wrong.mastered_at = datetime.now()
    else:
        if wrong is None:
            wrong = GxWrong(user_id=user_id, question_id=question.id,
                            user_answer=user_answer, wrong_count=1, correct_streak=0)
            db.add(wrong)
        else:
            wrong.wrong_count = (wrong.wrong_count or 0) + 1
            wrong.correct_streak = 0
            wrong.is_mastered = False
            wrong.mastered_at = None
            wrong.user_answer = user_answer
        wrong.last_wrong_at = datetime.now()
    db.commit()
    return {"is_correct": is_correct, "correct": question.answer or "",
            "analysis": question.analysis or ""}


def mark_mastered(db: Session, user_id: str, question_id: int) -> bool:
    """手动标记错题已掌握（不存在或已掌握返回 False）"""
    wrong = db.query(GxWrong).filter_by(user_id=user_id, question_id=question_id).first()
    if wrong is None or wrong.is_mastered:
        return False
    wrong.is_mastered = True
    wrong.mastered_at = datetime.now()
    db.commit()
    return True


def progress_overview(db: Session, user_id: str) -> dict:
    """分知识域进度总览：考纲全部知识域都列出（没学过的为 0），附汇总"""
    rows = {r.domain: r for r in
            db.query(GxProgress).filter_by(user_id=user_id).all()}
    domains = []
    total_q = total_c = total_case = total_read = 0
    for d in GX_DOMAINS:
        r = rows.get(d)
        qt, qc = (r.quiz_total or 0, r.quiz_correct or 0) if r else (0, 0)
        domains.append({
            "domain": d,
            "knowledge_read": (r.knowledge_read or 0) if r else 0,
            "quiz_total": qt, "quiz_correct": qc,
            "accuracy": round(qc / qt * 100) if qt else None,
            "case_count": (r.case_count or 0) if r else 0,
        })
        total_q += qt
        total_c += qc
        total_case += (r.case_count or 0) if r else 0
        total_read += (r.knowledge_read or 0) if r else 0
    return {"domains": domains,
            "summary": {"quiz_total": total_q, "quiz_correct": total_c,
                        "accuracy": round(total_c / total_q * 100) if total_q else None,
                        "case_count": total_case, "knowledge_read": total_read}}
