"""同步学服务层：单元导航 / 要点 / 同步练习 / 单元小测

单元标识约定：
- 英语：eng::{book_id}::{unit}
- 语文：chi::{semester}        （classical_texts 按年级+学期分组为一单元）
- 数学：math::{textbook_chapter}（problem_types.textbook_chapter，034 种子驱动）
- 初中六科（物理/化学/生物/道德与法治/历史/地理）：mid::{subject}::{unit}
  （middle_questions 已按章节标注 unit，037 种子驱动；语文/数学/英语沿用既有小学路径）

单元小测采用无状态签名 token：服务端生成题目时不下发答案，仅下发 HMAC 签名的
答案令牌；客户端提交答案后服务端验签并判分，避免答案泄露与篡改。
"""
import base64
import hashlib
import hmac
import json
import random
import re
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.word import Word, WordBook
from app.models.classical import ClassicalText
from app.models.problem_type import ProblemType
from app.models.middle import TeachingProgress, MiddleQuestion
from app.models.sync import SyncQuizLog
from app.services import semester as _semester
from app.config import QUIZ_SECRET

# 初中六科（middle_questions 题库支撑的同步学学科）
MIDDLE_SUBJECTS = ["物理", "化学", "生物", "道德与法治", "历史", "地理"]


def _is_middle(subject: str) -> bool:
    """是否由 middle_questions 题库支撑的初中学科（物理/化学/生物/道德与法治/历史/地理）"""
    return subject in MIDDLE_SUBJECTS

# ── 小测答案令牌（无状态签名）──
# 签名密钥来自 app/config.QUIZ_SECRET（由 .env 的 QUIZ_SECRET 配置，便于轮换），
# 不再硬编码于源码。默认值与历史值一致，存量签名令牌无需重新签发即可继续验签。



def _sign(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    b = base64.b64encode(raw).decode("ascii")
    sig = hmac.new(QUIZ_SECRET.encode(), b.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{b}.{sig}"


def _unsign(token: str) -> Optional[dict]:
    try:
        b, sig = token.rsplit(".", 1)
        exp = hmac.new(QUIZ_SECRET.encode(), b.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(exp, sig):
            return None
        return json.loads(base64.b64decode(b.encode()))
    except Exception:
        return None


# ── 单元标识编解码 ──
def _eng_unit(book_id: int, unit: str) -> str:
    return f"eng::{book_id}::{unit}"


def _chi_unit(semester: str) -> str:
    return f"chi::{semester}"


def _math_unit(chapter: str) -> str:
    return f"math::{chapter}"


def _mid_unit(subject: str, unit: str) -> str:
    return f"mid::{subject}::{unit}"


def _mid_subject_unit(unit: str):
    """解析 mid::{subject}::{unit} 返回 (subject, unit)"""
    _, subject, u = unit.split("::", 2)
    return subject, u


# ═══════════════════════════════════════════════════════════
# Overview
# ═══════════════════════════════════════════════════════════

def build_overview(db: Session, user_id: str, subject: str, grade: int,
                   include_next: bool = False) -> list:
    """返回某学科在当前年级下的单元列表（含状态/小测最佳/练习数）"""
    semesters = [_semester.current_semester()]
    if include_next:
        semesters.append(_semester.next_semester())

    if subject == "英语":
        units = _english_units(db, grade, semesters)
    elif subject == "语文":
        units = _chinese_units(db, grade, semesters)
    elif subject == "数学":
        # 初中(7年级及以上)数学走 middle_questions 题库；小学仍走 ProblemType 路径
        units = _middle_units(db, subject, grade) if grade >= 7 else _math_units(db, grade)
    elif _is_middle(subject):
        units = _middle_units(db, subject, grade)
    else:
        units = []

    # 聚合小测成绩
    logs = db.query(SyncQuizLog).filter(
        SyncQuizLog.user_id == user_id,
        SyncQuizLog.subject == subject,
    ).all()
    by_unit = {}
    for lg in logs:
        d = by_unit.setdefault(lg.unit, {"best": 0.0, "n": 0})
        d["best"] = max(d["best"], lg.score)
        d["n"] += 1

    out = []
    for u in units:
        info = by_unit.get(u["unit"], {"best": 0.0, "n": 0})
        best = info["best"]
        if info["n"] == 0:
            status = "未开始"
        elif best >= 80:
            status = "已过关"
        else:
            status = "进行中"
        out.append({
            "unit": u["unit"],
            "unit_label": u["unit_label"],
            "status": status,
            "quiz_best": best,
            "practice_done": info["n"],
            "total_quizzes": info["n"],
            "preview": u.get("preview", False),
        })
    return out


def _english_units(db: Session, grade: int, semesters) -> list:
    books = db.query(WordBook).filter(WordBook.grade == grade).all()
    out = []
    for b in books:
        if b.semester not in semesters and b.semester != "全":
            continue
        units = [u for (u,) in db.query(Word.unit).filter(
            Word.book_id == b.id, Word.unit != "", Word.unit.isnot(None),
        ).distinct().all()]
        for u in sorted(units, key=lambda x: _unit_key(x)):
            out.append({
                "unit": _eng_unit(b.id, u),
                "unit_label": f"{b.name} · {u}",
                "preview": b.semester not in [_semester.current_semester()],
            })
    return out


def _chinese_units(db: Session, grade: int, semesters) -> list:
    out = []
    # 按 (semester) 分组该年级篇目；学期不在当前范围则标为预习
    for sem in semesters:
        cnt = db.query(ClassicalText).filter(
            ClassicalText.grade == grade,
            (ClassicalText.semester == sem) | (ClassicalText.semester == "全"),
        ).count()
        if cnt == 0:
            continue
        out.append({
            "unit": _chi_unit(sem),
            "unit_label": f"语文 · {sem}学期（{cnt} 篇）",
            "preview": sem != _semester.current_semester(),
        })
    return out


def _math_units(db: Session, grade: int) -> list:
    rows = db.query(ProblemType.textbook_chapter).filter(
        ProblemType.textbook_chapter != "",
        ProblemType.textbook_chapter.isnot(None),
        ProblemType.grade_min <= grade,
        ProblemType.grade_max >= grade,
    ).distinct().all()
    chapters = [r[0] for r in rows]
    return [{"unit": _math_unit(c), "unit_label": c, "preview": False} for c in chapters]


def _unit_key(u: str):
    m = re.search(r"\d+", u or "")
    return (0, int(m.group())) if m else (1, u or "")


def _middle_units(db: Session, subject: str, grade: int) -> list:
    """初中六科单元：按 middle_questions 已标注的 unit 分组（037 种子驱动），
    仅取该学科在年级范围内的章节（年级范围 7<=题年级<=用户年级）。"""
    rows = db.query(MiddleQuestion.unit).filter(
        MiddleQuestion.subject == subject,
        MiddleQuestion.grade >= 7,
        MiddleQuestion.grade <= grade,
        MiddleQuestion.unit != "",
        MiddleQuestion.unit.isnot(None),
    ).distinct().order_by(MiddleQuestion.unit).all()
    units = [r[0] for r in rows]
    return [{"unit": _mid_unit(subject, u), "unit_label": u, "preview": False}
            for u in units]


# ═══════════════════════════════════════════════════════════
# 单元要点
# ═══════════════════════════════════════════════════════════

def build_unit_points(db: Session, subject: str, grade: int, unit: str) -> dict:
    if subject == "英语":
        _, book_id, u = unit.split("::", 2)
        words = db.query(Word).filter(
            Word.book_id == int(book_id), Word.unit == u,
        ).order_by(Word.id).limit(60).all()
        return {
            "subject": subject, "unit": unit, "kind": "word_list",
            "points": [{"word": w.word, "phonetic": w.phonetic or "",
                        "pos": w.pos or "", "meaning": w.meaning}
                       for w in words],
        }
    if subject == "语文":
        _, sem = unit.split("::", 1)
        texts = db.query(ClassicalText).filter(
            ClassicalText.grade == grade,
            (ClassicalText.semester == sem) | (ClassicalText.semester == "全"),
        ).order_by(ClassicalText.id).all()
        return {
            "subject": subject, "unit": unit, "kind": "text_list",
            "points": [{"id": t.id, "title": t.title, "author": t.author,
                        "dynasty": t.dynasty, "text_type": t.text_type}
                       for t in texts],
        }
    if subject == "数学":
        if grade >= 7:
            # 初中数学：直接展示该单元 middle_questions 题库条目作为要点
            _, _, u = unit.split("::", 2)
            qs = db.query(MiddleQuestion).filter(
                MiddleQuestion.subject == subject,
                MiddleQuestion.unit == u).order_by(MiddleQuestion.id).limit(80).all()
            return {
                "subject": subject, "unit": unit, "kind": "question_list",
                "points": [{"id": q.id, "question": q.question,
                            "answer": q.answer, "analysis": q.analysis or ""} for q in qs],
            }
        _, chapter = unit.split("::", 1)
        pts = db.query(ProblemType).filter(
            ProblemType.textbook_chapter == chapter).order_by(ProblemType.id).all()
        return {
            "subject": subject, "unit": unit, "kind": "type_list",
            "points": [{"code": p.code, "name": p.name,
                        "description": p.description or ""} for p in pts],
        }
    if _is_middle(subject):
        _, _, u = unit.split("::", 2)
        qs = db.query(MiddleQuestion).filter(
            MiddleQuestion.subject == subject,
            MiddleQuestion.unit == u,
        ).order_by(MiddleQuestion.id).limit(80).all()
        return {
            "subject": subject, "unit": unit, "kind": "question_list",
            "points": [{"id": q.id, "question": q.question,
                        "answer": q.answer, "analysis": q.analysis or ""}
                       for q in qs],
        }
    return {"subject": subject, "unit": unit, "points": []}


# ═══════════════════════════════════════════════════════════
# 同步练习（随做随判，含答案供本地判分）
# ═══════════════════════════════════════════════════════════

def build_unit_practice(db: Session, subject: str, grade: int, unit: str,
                        count: int = 10) -> dict:
    if subject == "英语":
        return _english_practice(db, unit, count)
    if subject == "语文":
        return _chinese_practice(db, grade, unit, count)
    if subject == "数学":
        if grade >= 7:
            return _middle_practice(db, subject, grade, unit, count)
        return _math_practice(db, grade, unit, count)
    if _is_middle(subject):
        return _middle_practice(db, subject, grade, unit, count)
    return {"subject": subject, "unit": unit, "items": []}


def _english_practice(db: Session, unit: str, count: int) -> dict:
    _, book_id, u = unit.split("::", 2)
    words = db.query(Word).filter(
        Word.book_id == int(book_id), Word.unit == u,
    ).order_by(Word.id).all()
    if not words:
        return {"subject": "英语", "unit": unit, "items": []}
    sample = words[:count] if len(words) <= count else random.sample(words, count)
    items = []
    for w in sample:
        # 中文释义 → 选英文单词（4 选 1）
        pool = [x.word for x in words if x.word != w.word]
        random.shuffle(pool)
        opts = [w.word] + pool[:3]
        random.shuffle(opts)
        items.append({
            "qid": w.id,
            "kind": "choice",
            "question": f"「{w.meaning}」对应的英文单词是？",
            "options": opts,
            "answer": w.word,
            "context": "",
        })
    return {"subject": "英语", "unit": unit, "items": items}


def _chinese_practice(db: Session, grade: int, unit: str, count: int) -> dict:
    _, sem = unit.split("::", 1)
    texts = db.query(ClassicalText).filter(
        ClassicalText.grade == grade,
        (ClassicalText.semester == sem) | (ClassicalText.semester == "全"),
    ).order_by(ClassicalText.id).all()
    if not texts:
        return {"subject": "语文", "unit": unit, "items": []}
    items = []
    for t in texts[:count]:
        lines = [ln for ln in (t.content or "").split("\n") if ln.strip()]
        if not lines:
            continue
        line = random.choice(lines)
        # 挖空一个 2-4 字片段（优先标点前的短语）
        spans = re.findall(r"[一-龥]{2,4}", line)
        spans = [s for s in spans if s != line.strip()]
        if not spans:
            continue
        blank = random.choice(spans)
        cloze = line.replace(blank, "（ ）", 1)
        items.append({
            "qid": t.id,
            "kind": "fill",
            "question": f"默写《{t.title}》中的句子，补全空缺：{cloze}",
            "answer": blank,
            "context": "",
        })
    return {"subject": "语文", "unit": unit, "items": items}


def _math_practice(db: Session, grade: int, unit: str, count: int) -> dict:
    from app.services.math_generator import generate_math_problems
    _, chapter = unit.split("::", 1)
    codes = [p.code for p in db.query(ProblemType).filter(
        ProblemType.textbook_chapter == chapter).all()]
    problems = generate_math_problems(
        grade=grade, problem_types=codes or None, count=count,
        include_answer=True, db=db)
    # 章节题型若无对应生成器（种子 code 尚未映射到生成器）时降级用全量生成器兜底
    if not problems and codes:
        problems = generate_math_problems(
            grade=grade, problem_types=None, count=count,
            include_answer=True, db=db)
    items = [{
        "qid": p.id,
        "kind": "fill",
        "question": p.question,
        "answer": p.answer,
        "context": p.type_name or "",
    } for p in problems]
    return {"subject": "数学", "unit": unit, "items": items}


def _middle_practice(db: Session, subject: str, grade: int, unit: str, count: int) -> dict:
    """初中六科同步练习：从 middle_questions 抽选择题（年级范围 7<=题年级<=用户年级）"""
    _, _, u = unit.split("::", 2)
    qs = db.query(MiddleQuestion).filter(
        MiddleQuestion.subject == subject,
        MiddleQuestion.unit == u,
        MiddleQuestion.grade >= 7,
        MiddleQuestion.grade <= grade,
    ).order_by(MiddleQuestion.id).all()
    if not qs:
        # 该章节未标注 unit 时退化为按学科抽题，保证有题可练
        qs = db.query(MiddleQuestion).filter(
            MiddleQuestion.subject == subject,
            MiddleQuestion.grade >= 7,
            MiddleQuestion.grade <= grade,
        ).order_by(MiddleQuestion.id).all()
    if not qs:
        return {"subject": subject, "unit": unit, "items": []}
    sample = qs if len(qs) <= count else random.sample(qs, count)
    items = []
    for q in sample:
        try:
            options = json.loads(q.options_json or "[]")
        except (json.JSONDecodeError, TypeError):
            options = []
        items.append({
            "qid": q.id,
            "kind": "choice",
            "question": q.question,
            "options": options,
            "answer": q.answer,
            "context": q.analysis or "",
        })
    return {"subject": subject, "unit": unit, "items": items}


# ═══════════════════════════════════════════════════════════
# 单元小测（无状态签名 token，服务端判分）
# ═══════════════════════════════════════════════════════════

def generate_unit_quiz(db: Session, subject: str, grade: int, unit: str,
                       count: int = 10) -> dict:
    """生成小测题目（不含答案），返回签名 token 供提交时验签判分"""
    practice = build_unit_practice(db, subject, grade, unit, count)
    items = practice.get("items", [])
    if not items:
        return {"subject": subject, "unit": unit, "questions": [], "token": ""}
    questions = []
    answers = []
    options_list = []
    for i, it in enumerate(items):
        answers.append(it["answer"])
        options_list.append(it.get("options", []))
        questions.append({
            "qid": i,
            "kind": it["kind"],
            "question": it["question"],
            "options": it.get("options", []),
        })
    token = _sign({"a": answers, "s": subject, "o": options_list})
    return {"subject": subject, "unit": unit, "questions": questions, "token": token}


def judge_unit_quiz(db: Session, user_id: str, subject: str, grade: int, unit: str,
                    token: str, answers: list) -> dict:
    """验签并判分，落库 sync_quiz_log，联动每日 *_sync 任务"""
    payload = _unsign(token)
    if not payload or payload.get("s") != subject:
        raise ValueError("小测令牌无效或已失效")
    correct_answers = payload.get("a", [])
    options_list = payload.get("o", [])
    # answers: [{qid, user_answer}]
    ans_map = {a.get("qid"): (a.get("user_answer") or "") for a in answers}
    total = len(correct_answers)
    correct = 0
    detail = []
    for qid, ca in enumerate(correct_answers):
        ua = ans_map.get(qid, "")
        ok = _judge_one(subject, ua, ca, options_list[qid] if qid < len(options_list) else [])
        if ok:
            correct += 1
        detail.append({"qid": qid, "correct": bool(ok),
                       "user_answer": ua, "correct_answer": ca})
    score = round(correct / total * 100, 1) if total else 0.0

    log = SyncQuizLog(
        user_id=user_id, subject=subject, grade=grade, unit=unit,
        score=score, total=total, correct=correct,
    )
    db.add(log)
    _mark_sync_task_done(db, user_id, subject)
    db.commit()
    db.refresh(log)
    return {
        "score": score, "total": total, "correct": correct,
        "passed": score >= 80, "detail": detail, "log_id": log.id,
    }


def _judge_one(subject: str, user_answer: str, correct_answer: str, options: list) -> bool:
    """判分：选择题（英语 + 初中六科，选项非空）按选项字母/文本匹配；
    填空（语文默写/数学计算）用容错匹配。"""
    ua = (user_answer or "").strip()
    ca = (correct_answer or "").strip()
    if not ua:
        return False
    # 选择题：选项非空时优先按字母 A-D 或选项文本匹配（兼容前端选项下标回传）
    if options:
        if len(ua) == 1 and ua.lower() in "abcd":
            idx = "abcd".index(ua.lower())
            if idx < len(options):
                return options[idx].strip().lower() == ca.strip().lower()
        return ua.lower() == ca.lower()
    # 填空容错（算式/单位/全角符号/顺序差异）
    from app.services.answer_check import fill_answer_correct
    return fill_answer_correct(ua, ca)


def _mark_sync_task_done(db: Session, user_id: str, subject: str):
    """D3 决议：单元小测提交 → 自动计完成对应科目的 *_sync 任务（无需家长确认）"""
    code_map = {"语文": "chi_sync", "数学": "math_sync", "英语": "eng_sync"}
    code = code_map.get(subject)
    if not code:
        return
    from app.models.daily_task import DailyTask
    today = date.today()
    row = db.query(DailyTask).filter(
        DailyTask.user_id == user_id,
        DailyTask.task_date == today,
        DailyTask.task_code == code,
    ).first()
    if row and row.status != "done":
        row.progress = row.target
        row.status = "done"
