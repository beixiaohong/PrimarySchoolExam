"""每日任务 API：每科必做 1 项，每科提供多个任务类型可更换

设计（与家长确认的规则）：
- 数学/语文/英语 三科每天各必完成 1 个任务（全部完成才算当天全勤）
- 每科有 3 个可选任务，孩子可以"换一个"循环切换
- 能自动核验的任务（做题/订正/背词/古诗文）由真实学习数据驱动进度，
  达到目标自动完成；需线下完成的任务（讲题/朗读/听写）提供"我完成了"按钮
- 连续全勤天数（streak）用于激励展示
"""
import logging
from datetime import date, datetime, time as dtime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.daily_task import DailyTask
from ..models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog

logger = logging.getLogger(__name__)

router = APIRouter()

SUBJECTS = ["数学", "语文", "英语"]

# 每科任务池（顺序即"换一个"的循环顺序）
TASK_POOLS = {
    "数学": [
        {"code": "math_exam", "title": "完成 1 套数学练习", "target": 1, "manual": False,
         "ico": "🧮", "desc": "刷题中心做一套数学试卷"},
        {"code": "math_fix", "title": "订正 2 道数学错题", "target": 2, "manual": False,
         "ico": "📕", "desc": "错题本重做或标记已掌握"},
        {"code": "math_teach", "title": "给家长讲 1 道题", "target": 1, "manual": True,
         "ico": "🎓", "desc": "挑一道今天的题讲给家长听"},
    ],
    "语文": [
        {"code": "chi_classical", "title": "背诵/默写 1 篇古诗文", "target": 1, "manual": False,
         "ico": "📜", "desc": "古诗文模块完成新背或复习"},
        {"code": "chi_exam", "title": "完成 1 套语文练习", "target": 1, "manual": False,
         "ico": "🖋️", "desc": "刷题中心做一套语文试卷"},
        {"code": "chi_read", "title": "朗读课文 5 分钟", "target": 1, "manual": True,
         "ico": "🎙️", "desc": "大声朗读课文或古诗，家长见证"},
    ],
    "英语": [
        {"code": "eng_vocab", "title": "学 5 个新单词", "target": 5, "manual": False,
         "ico": "🔤", "desc": "背单词模块完成 5 个新词"},
        {"code": "eng_exam", "title": "完成 1 套英语练习", "target": 1, "manual": False,
         "ico": "📝", "desc": "刷题中心做一套英语试卷"},
        {"code": "eng_dictation", "title": "听写 5 个单词", "target": 1, "manual": True,
         "ico": "✍️", "desc": "家长报词，孩子写出来"},
    ],
}


class SwapRequest(BaseModel):
    user_id: str
    subject: str


class ClaimRequest(BaseModel):
    user_id: str
    subject: str


def _today_start() -> datetime:
    return datetime.combine(date.today(), dtime.min)


def _today_attempts(db: Session, user_id: str, subject: str) -> int:
    """今天完成某学科练习（提交过试卷）的次数"""
    return db.query(ExamAttempt).join(ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id,
        ExamRecord.subject == subject,
        ExamAttempt.created_at >= _today_start(),
    ).count()


def _today_mastered(db: Session, user_id: str, subject: str) -> int:
    """今天订正（标记已掌握）某学科错题的数量"""
    return db.query(WrongRecord).join(Question, WrongRecord.question_id == Question.id).filter(
        WrongRecord.user_id == user_id,
        Question.subject == subject,
        WrongRecord.mastered_at != None,  # noqa: E711
        WrongRecord.mastered_at >= _today_start(),
    ).count()


def _task_progress(db: Session, user_id: str, subj: str, code: str) -> int:
    """根据真实学习数据计算自动任务的当前进度"""
    if code == "math_exam":
        return min(1, _today_attempts(db, user_id, "数学"))
    if code == "math_fix":
        return min(2, _today_mastered(db, user_id, "数学"))
    if code == "chi_exam":
        return min(1, _today_attempts(db, user_id, "语文"))
    if code == "chi_classical":
        log = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id,
            ClassicalDailyLog.learn_date == date.today(),
        ).first()
        v = (log.texts_learned + log.texts_reviewed) if log else 0
        return min(1, v)
    if code == "eng_exam":
        return min(1, _today_attempts(db, user_id, "英语"))
    if code == "eng_vocab":
        log = db.query(VocabDailyLog).filter(
            VocabDailyLog.user_id == user_id,
            VocabDailyLog.learn_date == date.today(),
        ).first()
        return min(5, log.new_words_learned if log else 0)
    return 0


def _ensure_today_rows(db: Session, user_id: str) -> dict:
    """确保今天三科任务行存在（默认取每科第一个任务）"""
    today = date.today()
    rows = {r.subject: r for r in db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today).all()}
    for subj in SUBJECTS:
        if subj not in rows:
            t = TASK_POOLS[subj][0]
            row = DailyTask(
                user_id=user_id, task_date=today, subject=subj,
                task_code=t["code"], title=t["title"], target=t["target"],
                progress=0, status="pending", manual=t["manual"],
            )
            db.add(row)
            rows[subj] = row
    db.commit()
    return rows


def _streak(db: Session, user_id: str) -> int:
    """连续全勤天数：三科全部完成的日子连续计数"""
    today = date.today()

    def _full(d: date) -> bool:
        rows = db.query(DailyTask).filter(
            DailyTask.user_id == user_id, DailyTask.task_date == d).all()
        return len(rows) >= len(SUBJECTS) and all(r.status == "done" for r in rows)

    streak = 0
    d = today if _full(today) else today - timedelta(days=1)
    while _full(d):
        streak += 1
        d -= timedelta(days=1)
        if streak > 3660:
            break
    return streak


def _build_payload(db: Session, user_id: str) -> dict:
    """刷新今日任务：计算进度、自动完成、汇总全勤与连续天数"""
    rows = _ensure_today_rows(db, user_id)
    for subj, row in rows.items():
        if row.status == "done":
            continue
        if not row.manual:
            prog = _task_progress(db, user_id, subj, row.task_code)
            row.progress = prog
            if prog >= row.target:
                row.status = "done"
    db.commit()

    tasks = []
    for subj in SUBJECTS:
        r = rows[subj]
        pool = TASK_POOLS[subj]
        idx = next((i for i, t in enumerate(pool) if t["code"] == r.task_code), 0)
        cur = pool[idx]
        nxt = pool[(idx + 1) % len(pool)]
        tasks.append({
            "subject": subj,
            "task_code": r.task_code,
            "title": r.title,
            "target": r.target,
            "progress": r.progress,
            "status": r.status,
            "manual": r.manual,
            "ico": cur["ico"],
            "desc": cur["desc"],
            "next_title": nxt["title"],
        })

    done_count = sum(1 for r in rows.values() if r.status == "done")
    return {
        "date": str(date.today()),
        "tasks": tasks,
        "done_count": done_count,
        "total": len(SUBJECTS),
        "streak_days": _streak(db, user_id),
    }


@router.get("/daily", summary="今日任务（每科必做，可更换）")
def get_daily(
    user_id: str = Query(..., description="用户名"),
    db: Session = Depends(get_db),
):
    return _build_payload(db, user_id)


@router.post("/daily/swap", summary="更换某学科今天的任务")
def swap_task(req: SwapRequest, db: Session = Depends(get_db)):
    if req.subject not in TASK_POOLS:
        raise HTTPException(400, "未知学科")
    today = date.today()
    rows = _ensure_today_rows(db, req.user_id)
    row = rows[req.subject]
    if row.status == "done":
        return _build_payload(db, req.user_id)  # 已完成的任务不允许更换
    pool = TASK_POOLS[req.subject]
    idx = next((i for i, t in enumerate(pool) if t["code"] == row.task_code), 0)
    nxt = pool[(idx + 1) % len(pool)]
    row.task_code = nxt["code"]
    row.title = nxt["title"]
    row.target = nxt["target"]
    row.manual = nxt["manual"]
    row.progress = 0
    row.status = "pending"
    db.commit()
    return _build_payload(db, req.user_id)


@router.post("/daily/claim", summary="手动确认完成某学科任务")
def claim_task(req: ClaimRequest, db: Session = Depends(get_db)):
    if req.subject not in TASK_POOLS:
        raise HTTPException(400, "未知学科")
    rows = _ensure_today_rows(db, req.user_id)
    row = rows[req.subject]
    if not row.manual:
        raise HTTPException(400, "该任务由学习数据自动判定，无需手动确认")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    row.progress = row.target
    row.status = "done"
    db.commit()
    return _build_payload(db, req.user_id)
