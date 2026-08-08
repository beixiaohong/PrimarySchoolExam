"""学习模块错题 + 今日任务汇总路由

错题打通：语法练习、古诗文默写等学习模块答错的题统一记入 study_errors，
与试卷错题（WrongRecord）一起在"错题本"中展示复习。

今日任务：汇总背单词/古诗文/语法/错题四个模块的待办数量，供首页使用。
"""
import json
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.study_error import StudyError
from ..models.exam import WrongRecord, Question, ExamAttempt
from ..models.vocab import VocabProgress, VocabDailyLog
from ..models.classical import ClassicalProgress, ClassicalDailyLog
from ..models.word import Word, WordBook
from ..models.classical import ClassicalText

router = APIRouter()


# ═══════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════

class StudyErrorItem(BaseModel):
    source_type: str  # grammar / classical
    source_id: int = 0
    module_name: str = ""
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    explanation: str = ""
    cause: str = ""  # 错因自评（可选）


class StudyErrorRecordRequest(BaseModel):
    user_id: str
    items: List[StudyErrorItem]


class StudyErrorMasterRequest(BaseModel):
    user_id: str
    error_id: int


# ═══════════════════════════════════════════════════════════
# 学习错题记录
# ═══════════════════════════════════════════════════════════

@router.post("/errors", summary="记录学习错题（批量，自动去重累计）")
def record_study_errors(req: StudyErrorRecordRequest, db: Session = Depends(get_db)):
    """记录学习模块错题。

    同一用户 + 来源 + 题目标识只保留一条记录，重复答错累计 error_count。
    """
    if not req.items:
        return {"recorded": 0}

    recorded = 0
    batch: dict = {}  # 批内去重：(source_type, source_id) → 记录对象（含本批新建），避免同批重复键触发唯一约束 500
    for item in req.items:
        if not item.question or not item.correct_answer:
            continue

        key = (item.source_type, item.source_id)
        if key not in batch:
            batch[key] = db.query(StudyError).filter(
                StudyError.user_id == req.user_id,
                StudyError.source_type == key[0],
                StudyError.source_id == key[1],
            ).first()
        existing = batch[key]

        if existing:
            # 已掌握后再次答错：重新激活（连击清零，闭环重新开始）
            existing.is_mastered = False
            existing.mastered_at = None
            existing.correct_streak = 0
            existing.error_count += 1
            existing.user_answer = item.user_answer
            existing.question = item.question
            existing.correct_answer = item.correct_answer
            existing.explanation = item.explanation
            if item.cause:
                existing.cause = item.cause
            if item.module_name:
                existing.module_name = item.module_name
            existing.wrong_at = date.today()
        else:
            rec = StudyError(
                user_id=req.user_id,
                source_type=item.source_type,
                source_id=item.source_id,
                module_name=item.module_name,
                question=item.question,
                user_answer=item.user_answer,
                correct_answer=item.correct_answer,
                explanation=item.explanation,
                cause=item.cause,
                error_count=1,
                wrong_at=date.today(),
            )
            db.add(rec)
            batch[key] = rec
        recorded += 1

    db.commit()
    return {"recorded": recorded}


@router.get("/errors", summary="查询学习错题列表")
def list_study_errors(
    user_id: str = Query(..., description="用户名"),
    source_type: Optional[str] = Query(None, description="过滤来源: grammar/classical"),
    subject: Optional[str] = Query(None, description="学科筛选: 英语→语法错题, 语文→古诗文错题, 数学→无学习错题"),
    only_pending: bool = Query(False, description="只看未掌握"),
    db: Session = Depends(get_db),
):
    q = db.query(StudyError).filter(StudyError.user_id == user_id)
    if subject:
        if subject == "英语":
            q = q.filter(StudyError.source_type.in_(["grammar", "vocab"]))
        elif subject == "语文":
            q = q.filter(StudyError.source_type == "classical")
        else:  # 学习错题仅来自英语语法/单词听写/语文古诗文，数学学科无学习错题
            q = q.filter(StudyError.id == -1)
    if source_type:
        q = q.filter(StudyError.source_type == source_type)
    if only_pending:
        q = q.filter(StudyError.is_mastered == False)  # noqa: E712
    errors = q.order_by(StudyError.wrong_at.desc(), StudyError.id.desc()).all()

    return [
        {
            "id": e.id,
            "source_type": e.source_type,
            "module_name": e.module_name or ({"grammar": "语法练习", "vocab": "单词听写"}.get(e.source_type, "古诗文默写")),
            "question": e.question,
            "user_answer": e.user_answer,
            "correct_answer": e.correct_answer,
            "explanation": e.explanation,
            "error_count": e.error_count,
            "is_mastered": e.is_mastered,
            "cause": e.cause or "",
            "wrong_at": str(e.wrong_at) if e.wrong_at else "",
        }
        for e in errors
    ]


@router.post("/errors/master", summary="标记学习错题已掌握")
def mark_study_error_mastered(req: StudyErrorMasterRequest, db: Session = Depends(get_db)):
    error = db.query(StudyError).filter(
        StudyError.id == req.error_id,
        StudyError.user_id == req.user_id,
    ).first()
    if not error:
        raise HTTPException(404, "错题记录不存在")
    error.is_mastered = True
    error.mastered_at = date.today()
    # 错题掌握 → 金币 +3（P2 金币宠物）
    try:
        from .pet import _grant_coins
        _grant_coins(db, req.user_id, 3, "错题掌握")
    except Exception:
        pass
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════
# 今日任务汇总（首页，全学科聚合）
# ═══════════════════════════════════════════════════════════

@router.get("/dashboard/today", summary="今日学习任务汇总（全学科聚合）")
def get_dashboard_today(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    subject: str = Query("英语", description="学科（兼容旧参数，用于返回单科视图）"),
    db: Session = Depends(get_db),
):
    """汇总今日所有模块待办，按学科聚合返回。

    subjects 字段包含 数学/英语/语文 三科各自的待办（今日首页一次拉取全部）；
    total_todo 为全部学科合计；
    vocab/classical/grammar/wrong 为兼容旧前端字段（按 subject 参数返回对应学科）。
    """
    today = date.today()
    subjects = {}
    total = 0
    for subj in ("英语", "数学", "语文"):
        task = _build_subject_task(db, user_id, grade, subj, today)
        subjects[subj] = task
        total += task["total_todo"]

    cur = subjects.get(subject, subjects["英语"])
    return {
        "date": str(today),
        "total_todo": total,
        "subjects": subjects,
        # ── 兼容旧字段 ──
        "vocab": cur["vocab"],
        "classical": cur["classical"],
        "grammar": cur["grammar"],
        "wrong": cur["wrong"],
    }


def _build_subject_task(db: Session, user_id: str, grade: int, subject: str, today: date) -> dict:
    """计算单个学科的今日任务

    学科归属：英语=背单词+语法练习，语文=古诗文，数学=无学习模块
    """
    # ── 背单词（仅英语科目展示） ──
    vocab = {"new_words": 0, "review_words": 0, "due_today": 0,
             "streak_days": 0, "learned": 0, "total": 0}
    if subject == "英语":
        book_ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
        if book_ids:
            word_ids_subq = db.query(Word.id).filter(Word.book_id.in_(book_ids))
            vocab["total"] = db.query(Word).filter(Word.book_id.in_(book_ids)).count()
            all_progress = db.query(VocabProgress).filter(
                VocabProgress.user_id == user_id,
                VocabProgress.word_id.in_(word_ids_subq),
            ).all()
            vocab["learned"] = len(all_progress)
            vocab["due_today"] = sum(
                1 for p in all_progress
                if p.status == "learning" and p.next_review_date and p.next_review_date <= today
            )
            today_log = db.query(VocabDailyLog).filter(
                VocabDailyLog.user_id == user_id,
                VocabDailyLog.learn_date == today,
            ).first()
            vocab["new_words"] = max(0, 20 - (today_log.new_words_learned if today_log else 0))
            vocab["review_words"] = vocab["due_today"]
            vocab["streak_days"] = _vocab_streak(db, user_id)

    # ── 古诗文（仅语文学科展示） ──
    classical = {"new_texts": 0, "review_texts": 0, "due_today": 0,
                 "streak_days": 0, "learned": 0, "total": 0}
    if subject == "语文":
        text_ids_subq = db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
        classical["total"] = db.query(ClassicalText).filter(ClassicalText.grade <= grade).count()
        c_progress = db.query(ClassicalProgress).filter(
            ClassicalProgress.user_id == user_id,
            ClassicalProgress.text_id.in_(text_ids_subq),
        ).all()
        classical["learned"] = len(c_progress)
        classical["due_today"] = sum(
            1 for p in c_progress
            if p.status == "learning" and p.next_review_date and p.next_review_date <= today
        )
        today_log = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id,
            ClassicalDailyLog.learn_date == today,
        ).first()
        new_done_today = today_log.texts_learned if today_log else 0
        classical["new_texts"] = max(0, 5 - new_done_today)
        classical["review_texts"] = classical["due_today"]
        classical["streak_days"] = _classical_streak(db, user_id)

    # ── 语法（仅英语科目展示） ──
    from ..models.grammar import GrammarExercise
    grammar = {"total_exercises": 0, "recent_wrong": 0}
    if subject == "英语":
        grammar = {
            "total_exercises": db.query(GrammarExercise).filter(
                GrammarExercise.grade <= grade
            ).count(),
            "recent_wrong": db.query(StudyError).filter(
                StudyError.user_id == user_id,
                StudyError.source_type == "grammar",
                StudyError.is_mastered == False,  # noqa: E712
            ).count(),
        }

    # ── 错题（按学科归属过滤） ──
    if subject == "英语":
        study_source = StudyError.source_type.in_(["grammar", "vocab"])
    elif subject == "语文":
        study_source = StudyError.source_type == "classical"
    else:
        study_source = StudyError.source_type.in_([])  # 数学无学习错题
    wrong = {
        "exam_pending": db.query(WrongRecord).join(
            Question, WrongRecord.question_id == Question.id
        ).filter(
            WrongRecord.user_id == user_id,
            WrongRecord.is_mastered == False,  # noqa: E712
            Question.subject == subject,
        ).count(),
        "study_pending": db.query(StudyError).filter(
            StudyError.user_id == user_id,
            StudyError.is_mastered == False,  # noqa: E712
            study_source,
        ).count(),
    }

    total_todo = (
        wrong["exam_pending"] + wrong["study_pending"]
        + (vocab["new_words"] + vocab["review_words"] if subject == "英语" else 0)
        + (classical["new_texts"] + classical["review_texts"] if subject == "语文" else 0)
    )

    return {
        "total_todo": total_todo,
        "vocab": vocab,
        "classical": classical,
        "grammar": grammar,
        "wrong": wrong,
    }


def _vocab_streak(db: Session, user_id: str) -> int:
    """连续学习天数（与 vocab 模块口径一致）"""
    logs = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id,
        VocabDailyLog.new_words_learned > 0,
    ).order_by(VocabDailyLog.learn_date.desc()).all()
    if not logs:
        return 0
    streak = 0
    check_date = date.today()
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date
    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


def _classical_streak(db: Session, user_id: str) -> int:
    """古诗文连续学习天数"""
    logs = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id,
        ClassicalDailyLog.texts_learned > 0,
    ).order_by(ClassicalDailyLog.learn_date.desc()).all()
    if not logs:
        return 0
    streak = 0
    check_date = date.today()
    if logs[0].learn_date < check_date:
        check_date = logs[0].learn_date
    log_dates = {log.learn_date for log in logs}
    while check_date in log_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


# ═══════════════════════════════════════════════════════════
# 错题练习提交（连续3次答对自动掌握）
# ═══════════════════════════════════════════════════════════

MASTER_STREAK = 3


class PracticeSubmitItem(BaseModel):
    kind: str  # exam / study
    record_id: int
    correct: bool
    # ── AI 判题复核字段（本地判错的题需携带，供 AI 复核改判） ──
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    subject: str = ""


class PracticeSubmitRequest(BaseModel):
    user_id: str
    results: List[PracticeSubmitItem]


@router.post("/practice-submit", summary="错题练习提交（整组全对直接掌握 / 单题累计 3 次掌握）")
def practice_submit(req: PracticeSubmitRequest, db: Session = Depends(get_db)):
    """错题练习结果回写（双轨统一，按 record_id 分组判定）：

    - 修正模式（同一 record_id 提交 ≥3 条）：整组全对 → 直接标记已掌握；
      组内任一条答错 → 整组失败（streak 清零、计数 +1、重新激活）
    - 兼容旧模式（单条提交）：答对 streak +1，累计 3 次掌握；答错清零重激活
    - AI 判题复核：本地判错且带作答内容的题批量送 AI，AI 判对 → 该条视为答对再分组
    """
    from datetime import datetime as _dt
    from collections import defaultdict

    # ── AI 判题复核（只升不降）：本地判错的题批量送 AI，AI 判对 → 改判正确 ──
    ai_approved: list = []
    ai_items = [
        {"key": i, "question": it.question, "answer": it.correct_answer,
         "user_answer": it.user_answer, "subject": it.subject}
        for i, it in enumerate(req.results)
        if not it.correct and (it.question or it.user_answer)
    ]
    if ai_items:
        from ..services.judge import judge_wrong_items
        approved = judge_wrong_items(db, req.user_id, ai_items)
        for i, it in enumerate(req.results):
            if i in approved:
                it.correct = True
                ai_approved.append(i)

    # AI 已判对的题：同步自动确认孩子对同错题记录的待处理申诉（避免家长端重复确认）
    if ai_approved:
        from ..models.appeal import AnswerAppeal
        from datetime import datetime as _dt
        auto_map = {req.results[i].record_id: req.results[i].user_answer for i in ai_approved}
        auto = db.query(AnswerAppeal).filter(
            AnswerAppeal.user_id == req.user_id,
            AnswerAppeal.status == "pending",
            AnswerAppeal.source == "retry",
            AnswerAppeal.record_id.in_(auto_map.keys()),
        ).all()
        for ap in auto:
            if auto_map.get(ap.record_id) == ap.user_answer:
                ap.status = "approved"
                ap.decided_at = _dt.now()

    updated = []
    groups = defaultdict(list)
    for item in req.results:
        groups[(item.kind, item.record_id)].append(item)

    for (kind, rid), items in groups.items():
        all_correct = all(it.correct for it in items)
        if kind == "exam":
            rec = db.query(WrongRecord).filter(
                WrongRecord.id == rid,
                WrongRecord.user_id == req.user_id,
            ).first()
            if not rec:
                continue
            if rec.is_unanswered:
                continue  # 未作答的题不走修正流程，需先通过 answer-unanswered 作答
            if len(items) >= 3:
                # 修正模式：整组判定（三道同类型全对才算修正）
                if all_correct:
                    rec.correct_streak = max(rec.correct_streak, MASTER_STREAK)
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.correct_streak = 0
                    rec.practice_count += 1
                    rec.is_mastered = False
                    rec.mastered_at = None
                    rec.wrong_at = _dt.now()
                    rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                    status = "reactivated"
            elif items[0].correct:
                rec.correct_streak = rec.correct_streak + 1
                if rec.correct_streak >= MASTER_STREAK:
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.next_review_date = None   # 答对即出队（明日复习队列只留「重做仍错」）
                    status = "streak"
            else:
                rec.correct_streak = 0
                rec.practice_count += 1
                rec.is_mastered = False
                rec.mastered_at = None
                rec.wrong_at = _dt.now()
                rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                status = "reactivated"
            updated.append({"kind": "exam", "record_id": rec.id,
                            "status": status, "streak": rec.correct_streak})
        elif kind == "study":
            rec = db.query(StudyError).filter(
                StudyError.id == rid,
                StudyError.user_id == req.user_id,
            ).first()
            if not rec:
                continue
            if len(items) >= 3:
                # 修正模式：整组判定
                if all_correct:
                    rec.correct_streak = max(rec.correct_streak, MASTER_STREAK)
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.correct_streak = 0
                    rec.error_count += 1
                    rec.is_mastered = False
                    rec.mastered_at = None
                    rec.wrong_at = _dt.now()
                    rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                    status = "reactivated"
            elif items[0].correct:
                rec.correct_streak = rec.correct_streak + 1
                if rec.correct_streak >= MASTER_STREAK:
                    rec.is_mastered = True
                    rec.mastered_at = _dt.now()
                    rec.next_review_date = None
                    status = "mastered"
                else:
                    rec.next_review_date = None   # 答对即出队（明日复习队列只留「重做仍错」）
                    status = "streak"
            else:
                rec.correct_streak = 0
                rec.error_count += 1
                rec.is_mastered = False
                rec.mastered_at = None
                rec.wrong_at = _dt.now()
                rec.next_review_date = date.today() + timedelta(days=1)   # 重做仍错 → 明天再来一次
                status = "reactivated"
            updated.append({"kind": "study", "record_id": rec.id,
                            "status": status, "streak": rec.correct_streak})

    # 重做掌握 → 金币 +3（P2 金币宠物）
    try:
        from .pet import _grant_coins
        if any(u["status"] == "mastered" for u in updated):
            _grant_coins(db, req.user_id, 3 * sum(1 for u in updated if u["status"] == "mastered"), "错题掌握")
    except Exception:
        pass
    db.commit()
    return {"updated": len(updated), "details": updated, "ai_approved": ai_approved}


# ═══════════════════════════════════════════════════════════
# 错因自评（双轨：试卷错题 WrongRecord + 学习错题 StudyError）
# ═══════════════════════════════════════════════════════════

CAUSE_LABELS = {
    "careless": "粗心大意",
    "concept": "概念不清",
    "method": "方法不会",
    "reading": "审题失误",
    "ai": "AI 讲解",
}


class CauseRequest(BaseModel):
    user_id: str
    kind: str  # exam / study
    record_id: int
    cause: str


@router.post("/cause", summary="提交错因自评")
def submit_cause(req: CauseRequest, db: Session = Depends(get_db)):
    """为一条错题记录标注错因（四选一），exam 指试卷错题，study 指学习错题"""
    if req.cause not in CAUSE_LABELS:
        raise HTTPException(400, f"错因无效，可选：{', '.join(CAUSE_LABELS.keys())}")

    if req.kind == "exam":
        rec = db.query(WrongRecord).filter(
            WrongRecord.id == req.record_id,
            WrongRecord.user_id == req.user_id,
        ).first()
    elif req.kind == "study":
        rec = db.query(StudyError).filter(
            StudyError.id == req.record_id,
            StudyError.user_id == req.user_id,
        ).first()
    else:
        raise HTTPException(400, "kind 仅支持 exam / study")

    if not rec:
        raise HTTPException(404, "错题记录不存在")

    rec.cause = req.cause
    db.commit()
    return {"ok": True, "cause": req.cause, "cause_label": CAUSE_LABELS[req.cause]}


class CauseByQuestionRequest(BaseModel):
    user_id: str
    question_id: int
    cause: str


@router.post("/cause-by-question", summary="按题目提交错因自评（答题中自评）")
def submit_cause_by_question(req: CauseByQuestionRequest, db: Session = Depends(get_db)):
    """试卷错题按 question_id 提交错因（答题完成后批量调用）"""
    if req.cause not in CAUSE_LABELS:
        raise HTTPException(400, f"错因无效，可选：{', '.join(CAUSE_LABELS.keys())}")
    rec = db.query(WrongRecord).filter(
        WrongRecord.user_id == req.user_id,
        WrongRecord.question_id == req.question_id,
    ).order_by(WrongRecord.id.desc()).first()
    if not rec:
        raise HTTPException(404, "该题暂不在错题本中")
    rec.cause = req.cause
    db.commit()
    return {"ok": True, "cause": req.cause, "cause_label": CAUSE_LABELS[req.cause]}


# ═══════════════════════════════════════════════════════════
# 自我超越（统计页 · 只和自己比）
# ═══════════════════════════════════════════════════════════

@router.get("/self-compare", summary="自我超越：最近两次做题/今昨背诵/本周错题对比")
def self_compare(
    user_id: str = Query(..., description="用户名"),
    subject: Optional[str] = Query(None, description="学科筛选（缺省全部）"),
    db: Session = Depends(get_db),
):
    today = date.today()
    yesterday = today - timedelta(days=1)

    # 1) 做题对比：最近两次（按提交时间）
    from ..models.exam import ExamRecord
    q = db.query(ExamAttempt, ExamRecord.title).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id)
    q = q.filter(ExamAttempt.user_id == user_id)
    if subject:
        q = q.filter(ExamRecord.subject == subject)
    rows = q.order_by(ExamAttempt.id.desc()).limit(2).all()
    attempts_cmp = None
    if len(rows) >= 2:
        (last, last_title), (prev, prev_title) = rows[0], rows[1]
        attempts_cmp = {
            "last_correct": last.correct, "prev_correct": prev.correct,
            "delta_correct": last.correct - prev.correct,
            "last_score": last.score, "prev_score": prev.score,
            "delta_score": last.score - prev.score,
            "last_title": last_title or "最近一次",
        }
    elif len(rows) == 1:
        attempts_cmp = {"last_correct": rows[0][0].correct, "prev_correct": None,
                        "delta_correct": None, "last_score": rows[0][0].score,
                        "prev_score": None, "delta_score": None,
                        "last_title": rows[0][1] or "最近一次"}

    # 2) 单词：今天 vs 昨天新学
    def day_new_words(d):
        rows = db.query(VocabDailyLog).filter(
            VocabDailyLog.user_id == user_id,
            VocabDailyLog.learn_date == d,
        ).all()
        return sum(r.new_words_learned or 0 for r in rows)

    new_words_today, new_words_yday = day_new_words(today), day_new_words(yesterday)

    # 3) 古诗文：今天 vs 昨天学习量
    def day_classical(d):
        rows = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id,
            ClassicalDailyLog.learn_date == d,
        ).all()
        return sum((r.texts_learned or 0) + (r.texts_reviewed or 0) for r in rows)

    cls_today, cls_yday = day_classical(today), day_classical(yesterday)

    # 4) 本周消灭错题（7 天内新掌握）
    week_ago = datetime.combine(today - timedelta(days=7), datetime.min.time())
    mastered_7d = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
        WrongRecord.is_mastered == True,  # noqa: E712
        WrongRecord.mastered_at >= week_ago,
    ).count()

    return {
        "attempts": attempts_cmp,
        "vocab": {"today": new_words_today, "yesterday": new_words_yday,
                  "delta": new_words_today - new_words_yday},
        "classical": {"today": cls_today, "yesterday": cls_yday,
                      "delta": cls_today - cls_yday},
        "mastered_7d": mastered_7d,
    }


# ═══════════════════════════════════════════════════════════
# 错因聚合分析（错题中心 · 错因分析页）
# ═══════════════════════════════════════════════════════════

@router.get("/errors/analysis", summary="错因聚合分析")
def analyze_errors(
    user_id: str = Query(..., description="用户名"),
    subject: Optional[str] = Query(None, description="学科筛选（缺省为全部学科）"),
    db: Session = Depends(get_db),
):
    """错因四选分布 + 来源分布 + 学科分布 + 掌握情况（双轨合并统计）"""
    sq = db.query(StudyError).filter(StudyError.user_id == user_id)
    wrq = db.query(WrongRecord).filter(WrongRecord.user_id == user_id).join(Question)
    if subject:
        if subject == "英语":
            sq = sq.filter(StudyError.source_type.in_(["grammar", "vocab"]))
        elif subject == "语文":
            sq = sq.filter(StudyError.source_type == "classical")
        else:  # 数学学科无学习错题
            sq = sq.filter(StudyError.id == -1)
        wrq = wrq.filter(Question.subject == subject)
    study_errors = sq.all()
    wrong_records = wrq.all()

    by_cause = {c: {"count": 0, "mastered": 0, "pending": 0, "label": label}
                for c, label in CAUSE_LABELS.items()}
    by_source = {}
    by_subject = {}
    pending_unlabeled = 0  # 未标注错因的待巩固错题

    def _count(cause: str, mastered: bool, source: str, subject: str):
        nonlocal pending_unlabeled
        if cause in by_cause:
            by_cause[cause]["count"] += 1
            if mastered:
                by_cause[cause]["mastered"] += 1
            else:
                by_cause[cause]["pending"] += 1
        elif not mastered:
            pending_unlabeled += 1
        by_source[source] = by_source.get(source, 0) + 1
        if subject:
            by_subject[subject] = by_subject.get(subject, 0) + 1

    for e in study_errors:
        _count(e.cause or "", e.is_mastered, e.source_type,
               "英语" if e.source_type == "grammar" else "语文")
    for wr in wrong_records:
        _count(wr.cause or "", wr.is_mastered, "exam", wr.question.subject)

    cause_list = [
        {"code": c, "label": d["label"], "count": d["count"],
         "mastered": d["mastered"], "pending": d["pending"]}
        for c, d in by_cause.items()
    ]
    cause_list.sort(key=lambda x: -x["count"])

    source_list = [{"code": k, "count": v} for k, v in by_source.items()]
    subject_list = [{"name": k, "count": v} for k, v in by_subject.items()]
    subject_list.sort(key=lambda x: -x["count"])

    total = len(study_errors) + len(wrong_records)
    mastered_total = sum(1 for e in study_errors if e.is_mastered) + \
        sum(1 for w in wrong_records if w.is_mastered)

    return {
        "total": total,
        "pending": total - mastered_total,
        "mastered": mastered_total,
        "mastery_rate": round(mastered_total / total * 100, 1) if total else 0,
        "pending_unlabeled": pending_unlabeled,
        "by_cause": cause_list,
        "by_source": source_list,
        "by_subject": subject_list,
    }


# ═══════════════════════════════════════════════════════════
# 错题变式重练（生成同考点相似题）
# ═══════════════════════════════════════════════════════════

class RetryRequest(BaseModel):
    user_id: str
    kind: str  # exam / study
    record_id: int
    count: int = 3


@router.post("/retry", summary="错题变式重练（生成相似题）")
def retry_wrong(req: RetryRequest, db: Session = Depends(get_db)):
    """根据错题类型生成同考点的变式题：

    - exam 试卷错题：同学科 + 同题型（type_code）随机抽题
    - study 语法错题：同语法点随机抽题
    - study 古诗文错题：同篇目其他句子生成默写
    统一返回 { questions: [{qid, question, options, answer, explanation, type_name, extra}] }，
    前端本地判分，答错的题可再次回写错题本。
    """
    import random as _random

    if req.kind == "exam":
        wr = db.query(WrongRecord).filter(
            WrongRecord.id == req.record_id,
            WrongRecord.user_id == req.user_id,
        ).first()
        if not wr:
            raise HTTPException(404, "试卷错题记录不存在")
        if wr.is_unanswered:
            raise HTTPException(400, "未作答的题请先在错题本中作答，不能直接修正")
        q = wr.question
        from ..models.exam import Question as Q
        candidates = db.query(Q).filter(
            Q.subject == q.subject,
            Q.type_code == q.type_code,
            Q.id != q.id,
        ).order_by(func.random()).limit(req.count).all()
        if len(candidates) < req.count:
            extra = db.query(Q).filter(
                Q.subject == q.subject,
                Q.id != q.id,
                Q.id.notin_([c.id for c in candidates]),
            ).order_by(func.random()).limit(req.count - len(candidates)).all()
            candidates = candidates + extra
        questions = [{
            "qid": c.id,
            "kind": "exam",
            "question": c.question,
            "options": _parse_options(c.options_json),
            "answer": c.answer,
            "explanation": "",
            "type_name": c.type_name or "",
            "image_path": c.image_path or "",
            "exam_id": c.exam_id,
        } for c in candidates]
        return {"kind": "exam", "module_name": q.type_name or "同类题",
                "count": len(questions), "questions": questions}

    # ── 学习错题 ──
    e = db.query(StudyError).filter(
        StudyError.id == req.record_id,
        StudyError.user_id == req.user_id,
    ).first()
    if not e:
        raise HTTPException(404, "学习错题记录不存在")

    if e.source_type == "grammar":
        from ..models.grammar import GrammarExercise, GrammarPoint
        ex = db.query(GrammarExercise).filter(GrammarExercise.id == e.source_id).first()
        if not ex:
            raise HTTPException(404, "原语法题不存在")
        candidates = db.query(GrammarExercise).filter(
            GrammarExercise.grammar_point_id == ex.grammar_point_id,
            GrammarExercise.id != ex.id,
        ).order_by(func.random()).limit(req.count).all()
        if len(candidates) < req.count:
            extra = db.query(GrammarExercise).filter(
                GrammarExercise.id != ex.id,
                GrammarExercise.id.notin_([c.id for c in candidates]),
            ).order_by(func.random()).limit(req.count - len(candidates)).all()
            candidates = candidates + extra
        point = db.query(GrammarPoint).filter(GrammarPoint.id == ex.grammar_point_id).first()
        questions = [{
            "qid": c.id,
            "kind": "study",
            "question": c.question,
            "options": _parse_options(c.options),
            "answer": c.answer,
            "explanation": c.explanation or "",
            "type_name": point.name if point else "语法练习",
        } for c in candidates]
        return {"kind": "study", "module_name": point.name if point else "语法练习",
                "count": len(questions), "questions": questions}

    if e.source_type == "classical":
        from ..models.classical import ClassicalText
        from ..routers.classical import _generate_quiz_from_text
        text = db.query(ClassicalText).filter(ClassicalText.id == e.source_id).first()
        if not text:
            raise HTTPException(404, "原篇目不存在")
        qs = _generate_quiz_from_text(text, req.count)
        questions = [{
            "qid": 0,
            "kind": "study",
            "question": q["question"],
            "options": [],
            "answer": q["answer"],
            "explanation": "",
            "type_name": "古诗文默写",
            "text_id": q["text_id"],
        } for q in qs]
        return {"kind": "study", "module_name": f"《{text.title}》默写",
                "count": len(questions), "questions": questions}

    if e.source_type == "vocab":
        from ..models.word import Word
        orig = db.query(Word).filter(Word.id == e.source_id).first()
        if not orig:
            raise HTTPException(404, "原单词不存在")
        # 从同一词册取其他单词作为候选
        candidates = db.query(Word).filter(
            Word.book_id == orig.book_id,
            Word.id != orig.id,
        ).order_by(func.random()).limit(req.count).all()
        if len(candidates) < req.count:
            extra = db.query(Word).filter(
                Word.id != orig.id,
                Word.id.notin_([c.id for c in candidates]),
            ).order_by(func.random()).limit(req.count - len(candidates)).all()
            candidates = candidates + extra
        questions = [{
            "qid": c.id,
            "kind": "study",
            "question": f"✍️ 听写：{c.pos + ' ' if c.pos else ''}{c.meaning}",
            "options": [],
            "answer": c.word,
            "explanation": "",
            "type_name": "单词听写",
        } for c in candidates]
        return {"kind": "study", "module_name": "单词听写重练",
                "count": len(questions), "questions": questions}

    raise HTTPException(400, "未知的错题来源")


def _parse_options(options_json: str) -> list:
    """解析选项 JSON 字符串，失败返回空列表"""
    if not options_json:
        return []
    try:
        data = json.loads(options_json)
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


# ═══════════════════════════════════════════════════════════
# 复习队列（遗忘曲线到期项，首页右侧队列）
# ═══════════════════════════════════════════════════════════

@router.get("/review-queue", summary="复习队列（遗忘曲线到期项）")
def review_queue(
    user_id: str = Query(..., description="用户名"),
    grade: int = Query(6, description="年级"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """汇总今日到期的单词 / 古诗文复习项，按到期时间升序

    items: [{type: vocab/classical, id, title, subtitle, due_date, stage, overdue_days}]
    """
    today = date.today()
    items = []

    # ── 单词到期 ──
    book_ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
    if book_ids:
        word_ids_subq = db.query(Word.id).filter(Word.book_id.in_(book_ids))
        due = db.query(VocabProgress).filter(
            VocabProgress.user_id == user_id,
            VocabProgress.status == "learning",
            VocabProgress.next_review_date <= today,
            VocabProgress.word_id.in_(word_ids_subq),
        ).order_by(VocabProgress.next_review_date.asc()).limit(limit).all()
        if due:
            words = {w.id: w for w in db.query(Word).filter(
                Word.id.in_([p.word_id for p in due])).all()}
            for p in due:
                w = words.get(p.word_id)
                if not w:
                    continue
                items.append({
                    "type": "vocab",
                    "id": p.id,
                    "title": w.word,
                    "subtitle": w.meaning,
                    "due_date": str(p.next_review_date) if p.next_review_date else "",
                    "stage": p.review_stage,
                    "overdue_days": (today - p.next_review_date).days if p.next_review_date else 0,
                })

    # ── 古诗文到期 ──
    text_ids_subq = db.query(ClassicalText.id).filter(ClassicalText.grade <= grade)
    due_c = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "learning",
        ClassicalProgress.next_review_date <= today,
        ClassicalProgress.text_id.in_(text_ids_subq),
    ).order_by(ClassicalProgress.next_review_date.asc()).limit(limit).all()
    if due_c:
        texts = {t.id: t for t in db.query(ClassicalText).filter(
            ClassicalText.id.in_([p.text_id for p in due_c])).all()}
        for p in due_c:
            t = texts.get(p.text_id)
            if not t:
                continue
            items.append({
                "type": "classical",
                "id": p.id,
                "title": f"《{t.title}》",
                "subtitle": f"{t.author} · {t.dynasty}",
                "due_date": str(p.next_review_date) if p.next_review_date else "",
                "stage": p.review_stage,
                "overdue_days": (today - p.next_review_date).days if p.next_review_date else 0,
            })

    items.sort(key=lambda x: (x["overdue_days"] > 0, x["due_date"]))

    # ── 未来 3 天到期数（供首页时间轴） ──
    upcoming = {"t1": 0, "t2": 0, "t3": 0}
    tomorrow = today + timedelta(days=1)
    for offset, key in ((1, "t1"), (2, "t2"), (3, "t3")):
        d = tomorrow + timedelta(days=offset - 1)
        upcoming[key] = (
            db.query(VocabProgress).filter(
                VocabProgress.user_id == user_id,
                VocabProgress.status == "learning",
                VocabProgress.next_review_date == d,
            ).count()
            + db.query(ClassicalProgress).filter(
                ClassicalProgress.user_id == user_id,
                ClassicalProgress.status == "learning",
                ClassicalProgress.next_review_date == d,
            ).count()
        )

    return {"date": str(today), "count": len(items), "items": items[:limit], "upcoming": upcoming}


# ═══════════════════════════════════════════════════════════
# 明日复习队列（PRD 3.3：重做仍错 → 明天再来一次）
# ═══════════════════════════════════════════════════════════

@router.get("/tomorrow-queue", summary="明日复习队列（重做仍错，建议明天再战的错题）")
def tomorrow_queue(
    user_id: str = Query(..., description="用户名"),
    subject: str = Query(None, description="学科筛选（数学/语文/英语，学习错题无学科概念时忽略）"),
    db: Session = Depends(get_db),
):
    """重做仍错的错题进入明日复习队列（next_review_date 非空且未掌握）。

    items: [{kind: exam/study, record_id, question, subject, module_name, cause, next_review_date}]
    """
    today = date.today()
    items = []

    # ── 试卷错题（wrong_records）──
    recs = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id,
        WrongRecord.next_review_date.isnot(None),
        WrongRecord.is_mastered.is_(False),
    ).all()
    if recs:
        qids = list({r.question_id for r in recs})
        qmap = {q.id: q for q in db.query(Question).filter(Question.id.in_(qids)).all()} if qids else {}
        for r in recs:
            q = qmap.get(r.question_id)
            if not q:
                continue
            if subject and q.subject != subject:
                continue
            items.append({
                "kind": "exam", "record_id": r.id,
                "question": q.question, "subject": q.subject,
                "module_name": q.type_name or "", "cause": r.cause or "",
                "next_review_date": str(r.next_review_date) if r.next_review_date else "",
            })

    # ── 学习错题（study_errors）──
    for r in db.query(StudyError).filter(
        StudyError.user_id == user_id,
        StudyError.next_review_date.isnot(None),
        StudyError.is_mastered.is_(False),
    ).all():
        items.append({
            "kind": "study", "record_id": r.id,
            "question": r.question, "subject": "语文" if r.source_type == "classical" else "英语",
            "module_name": r.module_name or "", "cause": r.cause or "",
            "next_review_date": str(r.next_review_date) if r.next_review_date else "",
        })

    items.sort(key=lambda x: x["next_review_date"])
    return {"date": str(today), "count": len(items), "items": items}
