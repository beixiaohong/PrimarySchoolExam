"""每日任务 API：每科必做 1 项，每科提供多个任务类型可更换

设计（与家长确认的规则）：
- 数学/语文/英语 三科每天各必完成 1 个任务（全部完成才算当天全勤）
- 每科有 3 个可选任务，孩子可以"换一个"循环切换
- 能自动核验的任务（做题/订正/背词/古诗文）由真实学习数据驱动进度，
  达到目标自动完成；需线下完成的任务（讲题/朗读/听写）提供"我完成了"按钮
- 任务目标数量（如"做几套练习""学几个新词"）由家长在家长面板配置，
  未配置时使用下方默认值（家长设置明天及以后的任务生效，
  今天的未完成任务也会同步更新）
- 连续全勤天数（streak）用于激励展示
"""
import json
import logging
import re
from datetime import date, datetime, time as dtime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.daily_task import DailyTask
from ..models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog
from ..models.study_error import StudyError

logger = logging.getLogger(__name__)

router = APIRouter()

SUBJECTS = ["数学", "语文", "英语"]

# 每科任务池（顺序即"换一个"的循环顺序）
TASK_POOLS = {
    "数学": [
        {"code": "math_exam", "title": "完成 1 套数学练习", "target": 1, "manual": False,
         "ico": "🧮", "desc": "刷题中心做一套数学试卷"},
        {"code": "math_fix", "title": "订正 10 道数学错题", "target": 10, "manual": False,
         "ico": "📕", "desc": "错题本重做或标记已掌握（每道需做3道同类型题全对才算修正）"},
        {"code": "math_review", "title": "复习 5 道昨日数学错题", "target": 5, "manual": False,
         "ico": "🔄", "desc": "把昨天做错的数学题重做一遍"},
        {"code": "math_teach", "title": "给家长讲 1 道题", "target": 1, "manual": True,
         "ico": "🎓", "desc": "挑一道今天的题讲给家长听"},
    ],
    "语文": [
        {"code": "chi_classical", "title": "背诵古诗文（含新背+复习）", "target": 1, "manual": False,
         "ico": "📜", "desc": "背诵中心完成新背或复习，每日必选"},
        {"code": "chi_exam", "title": "完成 1 套语文练习", "target": 1, "manual": False,
         "ico": "🖋️", "desc": "刷题中心做一套语文试卷"},
        {"code": "chi_review", "title": "复习 5 道昨日语文错题", "target": 5, "manual": False,
         "ico": "🔄", "desc": "把昨天做错的语文题重做一遍"},
        {"code": "chi_read", "title": "朗读课文 5 分钟", "target": 5, "manual": True,
         "ico": "🎙️", "desc": "大声朗读课文或古诗，完成后由家长确认"},
    ],
    "英语": [
        {"code": "eng_vocab", "title": "学单词（含新学+复习）", "target": 5, "manual": False,
         "ico": "🔤", "desc": "背单词模块完成新学或复习，每日必选"},
        {"code": "eng_exam", "title": "完成 1 套英语练习", "target": 1, "manual": False,
         "ico": "📝", "desc": "刷题中心做一套英语试卷"},
        {"code": "eng_review", "title": "复习 5 道昨日英语错题", "target": 5, "manual": False,
         "ico": "🔄", "desc": "把昨天做错的英语题重做一遍"},
        {"code": "eng_dictation", "title": "听写 5 个单词", "target": 5, "manual": True,
         "ico": "✍️", "desc": "家长报词孩子写出来，完成后由家长确认"},
    ],
}

# 家长可配置目标数量的任务（自动任务由学习数据自动判定完成；
# 手动任务 [讲题/朗读/听写] 无法自动核验，家长在家长面板设置数量，
# 孩子完成后由家长在家长面板点「确认完成」）
CONFIGURABLE_CODES = ["math_exam", "math_fix", "math_review", "chi_exam", "chi_classical", "chi_review",
                      "eng_exam", "eng_vocab", "eng_review",
                      "math_teach", "chi_read", "eng_dictation"]
MIN_TARGET, MAX_TARGET = 1, 50

# 必选任务：不允许被「换一个」替换，每天必须完成
MANDATORY_CODES = {"chi_classical", "eng_vocab"}

# 练习类任务（math_exam / chi_exam / eng_exam）的完成门槛：
# 只有正确率 ≥60% 的提交才计入完成进度（与家长确认：当日任务完成需正确率达标，直接提交不行）
TASK_PASS_SCORE = 60


def _default_target(code: str) -> int:
    for subj, pool in TASK_POOLS.items():
        for t in pool:
            if t["code"] == code:
                return t["target"]
    return 1


# ═══════════════ 家长设置（每日任务题目数量） ═══════════════

def _load_settings(db: Session, user_id: str) -> dict:
    """读取家长设置：{task_code: target}，只含用户覆盖过的项"""
    row = db.execute(
        text("SELECT settings_json FROM parent_task_settings WHERE user_id=:u"),
        {"u": user_id}).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row[0] or "{}")
        if not isinstance(data, dict):
            return {}
        return {k: int(v) for k, v in data.items()
                if k in CONFIGURABLE_CODES and isinstance(v, (int, float))
                and MIN_TARGET <= int(v) <= MAX_TARGET}
    except Exception:
        return {}


def _setting_target(settings: dict, code: str) -> int | None:
    """设置值（未覆盖返回 None，调用方回落到默认值；浮点/字符串数值统一取整）"""
    val = settings.get(code)
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _display_title(pool_title: str, target: int, default_target: int) -> str:
    """标题里的数量跟随家长设置：如"完成 1 套数学练习" + 目标 3 → "完成 3 套数学练习" """
    if target == default_target:
        return pool_title
    return re.sub(r"\d+", str(target), pool_title, count=1)


class SettingsRequest(BaseModel):
    user_id: str
    settings: dict = Field(default_factory=dict,
                           description='{"task_code": target}，仅需传想修改的项')


@router.get("/settings", summary="获取每日任务目标数量（家长可配置项）")
def get_task_settings(
    user_id: str = Query(..., description="用户名"),
    db: Session = Depends(get_db),
):
    """返回全部可配置项的当前生效值（家长覆盖或默认值）"""
    user = _load_settings(db, user_id)
    items = []
    for code in CONFIGURABLE_CODES:
        subj = next(s for s, pool in TASK_POOLS.items()
                    if any(t["code"] == code for t in pool))
        item = next(t for t in TASK_POOLS[subj] if t["code"] == code)
        items.append({
            "code": code,
            "subject": subj,
            "title": item["title"],
            "default": item["target"],
            "target": user.get(code, item["target"]),
        })
    return {"items": items}


@router.post("/settings", summary="保存每日任务目标数量（家长设置）")
def save_task_settings(req: SettingsRequest, db: Session = Depends(get_db)):
    """保存家长设置：校验 1-50 整数；同步更新今天未完成任务行的目标数量。

    说明：家长设置优先于任务池默认值；今天的任务行（未完成）会立即
    更新目标，已完成的不再追溯；明天起的任务按新设置生成。
    """
    if not isinstance(req.settings, dict):
        raise HTTPException(400, "settings 必须为对象")
    clean = {}
    for code, val in req.settings.items():
        if code not in CONFIGURABLE_CODES:
            raise HTTPException(400, f"不支持的任务类型: {code}")
        try:
            v = int(val)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{code} 的目标数量必须是整数")
        if not MIN_TARGET <= v <= MAX_TARGET:
            raise HTTPException(400, f"{code} 的目标数量需在 {MIN_TARGET}-{MAX_TARGET} 之间")
        clean[code] = v
    if not clean:
        return get_task_settings(req.user_id, db)

    # 合并保存（与已有设置合并，保留未修改项）
    merged = _load_settings(db, req.user_id)
    merged.update(clean)
    db.execute(text(
        "INSERT INTO parent_task_settings (user_id, settings_json, updated_at) "
        "VALUES (:u, :j, :t) "
        "ON CONFLICT(user_id) DO UPDATE SET settings_json=:j, updated_at=:t"),
        {"u": req.user_id, "j": json.dumps(merged), "t": datetime.now()})
    # 同步更新今天未完成任务行的目标
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == req.user_id, DailyTask.task_date == today).all()
    for r in rows:
        if r.status != "done" and r.task_code in clean:
            r.target = clean[r.task_code]
    db.commit()
    return get_task_settings(req.user_id, db)


class SwapRequest(BaseModel):
    user_id: str
    subject: str


class ClaimRequest(BaseModel):
    user_id: str
    subject: str


def _today_start() -> datetime:
    return datetime.combine(date.today(), dtime.min)


def _today_attempts(db: Session, user_id: str, subject: str) -> int:
    """今天正确率 ≥TASK_PASS_SCORE 的练习提交次数。

    低于门槛的提交（正确率不够）不推进任务进度——做题记录照常保存
    （错题本、学习统计仍依赖它），只是不算"完成任务"。
    """
    return db.query(ExamAttempt).join(ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id,
        ExamRecord.subject == subject,
        ExamAttempt.score >= TASK_PASS_SCORE,
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


def _yesterday_start() -> datetime:
    return datetime.combine(date.today() - timedelta(days=1), dtime.min)


def _yesterday_end() -> datetime:
    return datetime.combine(date.today(), dtime.min)


def _yesterday_reviewed(db: Session, user_id: str, subject: str) -> int:
    """昨天做错的题中，今天已复习（掌握或练习过）的数量。

    覆盖 WrongRecord（试卷错题）+ StudyError（学习模块错题）。
    """
    # 试卷错题：昨天错的，今天已掌握
    exam_reviewed = db.query(WrongRecord).join(Question, WrongRecord.question_id == Question.id).filter(
        WrongRecord.user_id == user_id,
        Question.subject == subject,
        WrongRecord.wrong_at >= _yesterday_start(),
        WrongRecord.wrong_at < _yesterday_end(),
        WrongRecord.is_mastered == True,  # noqa: E712
        WrongRecord.mastered_at >= _today_start(),
    ).count()
    # 学习模块错题：昨天错的，今天已掌握
    source_map = {"数学": [], "英语": ["grammar", "vocab"], "语文": ["classical"]}
    types = source_map.get(subject, [])
    study_reviewed = 0
    if types:
        study_reviewed = db.query(StudyError).filter(
            StudyError.user_id == user_id,
            StudyError.source_type.in_(types),
            StudyError.wrong_at >= _yesterday_start(),
            StudyError.wrong_at < _yesterday_end(),
            StudyError.is_mastered == True,  # noqa: E712
            StudyError.mastered_at >= _today_start(),
        ).count()
    return exam_reviewed + study_reviewed


def _task_progress(db: Session, user_id: str, subj: str, code: str, target: int) -> int:
    """根据真实学习数据计算自动任务的当前进度（封顶为任务目标）"""
    if code == "math_exam":
        return min(target, _today_attempts(db, user_id, "数学"))
    if code == "math_fix":
        return min(target, _today_mastered(db, user_id, "数学"))
    if code == "chi_exam":
        return min(target, _today_attempts(db, user_id, "语文"))
    if code == "chi_classical":
        log = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id,
            ClassicalDailyLog.learn_date == date.today(),
        ).first()
        v = ((log.texts_learned or 0) + (log.texts_reviewed or 0)) if log else 0
        return min(target, v)
    if code == "eng_exam":
        return min(target, _today_attempts(db, user_id, "英语"))
    if code == "eng_vocab":
        log = db.query(VocabDailyLog).filter(
            VocabDailyLog.user_id == user_id,
            VocabDailyLog.learn_date == date.today(),
        ).first()
        v = ((log.new_words_learned or 0) + (log.words_reviewed or 0)) if log else 0
        return min(target, v)
    if code == "math_review":
        return min(target, _yesterday_reviewed(db, user_id, "数学"))
    if code == "chi_review":
        return min(target, _yesterday_reviewed(db, user_id, "语文"))
    if code == "eng_review":
        return min(target, _yesterday_reviewed(db, user_id, "英语"))
    return 0


def _ensure_today_rows(db: Session, user_id: str) -> dict:
    """确保今天三科任务行存在（默认取每科第一个任务，目标数量应用家长设置）"""
    today = date.today()
    rows = {r.subject: r for r in db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today).all()}
    settings = _load_settings(db, user_id)
    for subj in SUBJECTS:
        if subj not in rows:
            t = TASK_POOLS[subj][0]
            row = DailyTask(
                user_id=user_id, task_date=today, subject=subj,
                task_code=t["code"], title=t["title"],
                target=_setting_target(settings, t["code"]) or t["target"],
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
    settings = _load_settings(db, user_id)
    # 遗留修复：旧版本写入的 task_code 若已不在任务池（如任务池调整），
    # 展示与进度都会按池内第一个任务处理，这里同步回写存储，避免永久 pending 卡死
    for subj, row in rows.items():
        pool = TASK_POOLS[subj]
        if not any(t["code"] == row.task_code for t in pool) and row.status != "done":
            cur = pool[0]
            row.task_code = cur["code"]
            row.title = cur["title"]
            row.target = _setting_target(settings, cur["code"]) or cur["target"]
            row.manual = cur["manual"]
            row.progress = 0
    for subj, row in rows.items():
        if row.status == "done":
            continue
        if not row.manual:
            prog = _task_progress(db, user_id, subj, row.task_code, row.target)
            row.progress = prog
            if prog >= row.target:
                row.status = "done"
                # 任务完成 → 进行中心愿进度 +1（Sprint 3 奖励闭环）
                try:
                    from .rewards import inc_active_wish_progress
                    inc_active_wish_progress(db, user_id, 1)
                except Exception:
                    pass
    db.commit()

    # 全勤日 → 需天数的兑换券累计 1 天进度（同日去重，达标自动获得 1 张）
    try:
        from .rewards import sync_coupon_progress
        sync_coupon_progress(db, user_id)
    except Exception:
        pass

    tasks = []
    for subj in SUBJECTS:
        r = rows[subj]
        pool = TASK_POOLS[subj]
        idx = next((i for i, t in enumerate(pool) if t["code"] == r.task_code), 0)
        cur = pool[idx]
        nxt = pool[(idx + 1) % len(pool)]
        nxt_target = _setting_target(settings, nxt["code"]) or nxt["target"]
        tasks.append({
            "subject": subj,
            "task_code": r.task_code,
            "title": _display_title(cur["title"], r.target, cur["target"]),
            "target": r.target,
            "progress": r.progress,
            "status": r.status,
            "manual": r.manual,
            "mandatory": r.task_code in MANDATORY_CODES,
            "ico": cur["ico"],
            "desc": cur["desc"],
            "next_title": _display_title(nxt["title"], nxt_target, nxt["target"]),
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
    if row.task_code in MANDATORY_CODES:
        raise HTTPException(400, "该任务为每日必选，不可更换")
    pool = TASK_POOLS[req.subject]
    idx = next((i for i, t in enumerate(pool) if t["code"] == row.task_code), 0)
    nxt = pool[(idx + 1) % len(pool)]
    settings = _load_settings(db, req.user_id)
    row.task_code = nxt["code"]
    row.title = nxt["title"]
    row.target = _setting_target(settings, nxt["code"]) or nxt["target"]
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
    # 任务完成 → 进行中心愿进度 +1（Sprint 3 奖励闭环）
    try:
        from .rewards import inc_active_wish_progress
        inc_active_wish_progress(db, req.user_id, 1)
    except Exception:
        pass
    # 任务完成 → 金币 +5（P2 金币宠物）
    try:
        from .pet import _grant_coins
        _grant_coins(db, req.user_id, 5, "完成任务")
    except Exception:
        pass
    db.commit()
    return _build_payload(db, req.user_id)
