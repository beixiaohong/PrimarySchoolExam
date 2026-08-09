"""每日任务 API：3 强制 + 3 可选双轨制

强制任务（每科 1 条，固定不变）：
- 数学：完成 1 套数学练习
- 语文：背诵古诗文（含新背+复习）
- 英语：学单词（含新学+复习）
→ 三科强制全部完成 = 当天全勤，计入卡券进度

可选任务（系统每日从任务池随机生成 3 条）：
→ 全部完成获得 1 张补签卡（可补签中断日）
→ 不可更换，系统自动分配
"""
import hashlib
import json
import logging
import re
from datetime import date, datetime, time as dtime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.daily_task import DailyTask
from ..models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog
from ..models.study_error import StudyError
from ..models.makeup_card import MakeupCard, MakeupUsageLog

logger = logging.getLogger(__name__)

router = APIRouter()

SUBJECTS = ["数学", "语文", "英语"]

# ═══════════════ 强制任务（每科固定 1 条，不可更换） ═══════════════

MANDATORY_TASKS = {
    "数学": {"code": "math_exam", "title": "完成 1 套数学练习", "target": 1, "manual": False,
             "ico": "🧮", "desc": "刷题中心做一套数学试卷"},
    "语文": {"code": "chi_classical", "title": "背诵古诗文（含新背+复习）", "target": 1, "manual": False,
             "ico": "📜", "desc": "背诵中心完成新背和复习"},
    "英语": {"code": "eng_vocab", "title": "学单词（含新学+复习）", "target": 5, "manual": False,
             "ico": "🔤", "desc": "背单词模块完成新学和复习"},
}

# ═══════════════ 可选任务池（系统每日随机抽 3 条） ═══════════════

OPTIONAL_POOL = [
    # 数学
    {"code": "math_fix", "title": "订正 10 道数学错题", "target": 10, "manual": False,
     "ico": "📕", "desc": "错题本重做或标记已掌握", "subject": "数学"},
    {"code": "math_teach", "title": "给家长讲 1 道题", "target": 1, "manual": True,
     "ico": "🎓", "desc": "挑一道今天的题讲给家长听", "subject": "数学"},
    {"code": "math_challenge", "title": "数学 60 秒挑战赛 1 次", "target": 1, "manual": False,
     "ico": "⚡", "desc": "限时挑战赛，60 秒内尽可能多答对", "subject": "数学"},
    {"code": "math_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成数学同步练习后，找家长确认", "subject": "数学"},
    # 语文
    {"code": "chi_exam", "title": "完成 1 套语文练习", "target": 1, "manual": False,
     "ico": "🖋️", "desc": "刷题中心做一套语文试卷", "subject": "语文"},
    {"code": "chi_read", "title": "朗读课文 5 分钟", "target": 5, "manual": True,
     "ico": "🎙️", "desc": "大声朗读课文或古诗，完成后由家长确认", "subject": "语文"},
    {"code": "chi_dictation", "title": "默写 3 首古诗", "target": 3, "manual": False,
     "ico": "✍️", "desc": "在背诵中心完成古诗文默写", "subject": "语文"},
    {"code": "chi_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成语文同步练习后，找家长确认", "subject": "语文"},
    # 英语
    {"code": "eng_exam", "title": "完成 1 套英语练习", "target": 1, "manual": False,
     "ico": "📝", "desc": "刷题中心做一套英语试卷", "subject": "英语"},
    {"code": "eng_dictation", "title": "听写 10 个单词", "target": 10, "manual": False,
     "ico": "👂", "desc": "在听写磨耳朵完成单词听写", "subject": "英语"},
    {"code": "eng_challenge", "title": "英语 60 秒挑战赛 1 次", "target": 1, "manual": False,
     "ico": "⚡", "desc": "限时挑战赛，60 秒内尽可能多答对", "subject": "英语"},
    {"code": "eng_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成英语同步练习后，找家长确认", "subject": "英语"},
]

# 家长可配置目标数量的任务
CONFIGURABLE_CODES = [t["code"] for t in [
    MANDATORY_TASKS["数学"], MANDATORY_TASKS["语文"], MANDATORY_TASKS["英语"],
]] + [t["code"] for t in OPTIONAL_POOL]
# 去重
CONFIGURABLE_CODES = list(dict.fromkeys(CONFIGURABLE_CODES))

MIN_TARGET, MAX_TARGET = 1, 50

# 练习类任务的完成门槛
TASK_PASS_SCORE = 60


# ═══════════════ 每日可选任务生成（确定性随机） ═══════════════

def _pick_daily_optional(user_id: str, today: date, settings: dict = None) -> list:
    """基于日期+用户名确定性随机选 3 条可选任务（同一天同一用户结果固定）"""
    seed = f"{user_id}:{today}:{'daily-optional'}"
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    # 过滤掉已禁用的任务
    pool = [t for t in OPTIONAL_POOL if _is_task_enabled(settings or {}, t["code"])]
    if not pool:
        pool = list(OPTIONAL_POOL)  # 全部禁用时回退到全量
    picked = []
    for i in range(3):
        idx = (h >> (i * 8)) % len(pool)
        picked.append(pool.pop(idx))
        if not pool:
            pool = [t for t in OPTIONAL_POOL if _is_task_enabled(settings or {}, t["code"])]
            if not pool:
                pool = list(OPTIONAL_POOL)
    return picked


# ═══════════════ 工具函数 ═══════════════

def _default_target(code: str) -> int:
    for t in list(MANDATORY_TASKS.values()) + OPTIONAL_POOL:
        if t["code"] == code:
            return t["target"]
    return 1


def _display_title(pool_title: str, target: int, default_target: int) -> str:
    if target == default_target:
        return pool_title
    # 替换最后一个数字（避免误改固定数值如"60秒"）
    parts = re.split(r"(\d+)", pool_title)
    # parts 交替 [文本, 数字, 文本, 数字, ...]，从后往前找第一个数字段
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].isdigit():
            parts[i] = str(target)
            break
    return "".join(parts)


# ═══════════════ 家长设置 ═══════════════

def _load_settings(db: Session, user_id: str) -> dict:
    row = db.execute(
        text("SELECT settings_json FROM parent_task_settings WHERE user_id=:u"),
        {"u": user_id}).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row[0] or "{}")
        if not isinstance(data, dict):
            return {}
        # 新格式：嵌套结构 {"targets": {...}, "enabled": {...}, "mandatory": {...}}
        if "targets" in data and isinstance(data["targets"], dict):
            targets = {k: int(v) for k, v in data["targets"].items()
                       if k in CONFIGURABLE_CODES and isinstance(v, (int, float))
                       and MIN_TARGET <= int(v) <= MAX_TARGET}
            return {
                "targets": targets,
                "enabled": data.get("enabled", {}),  # {code: bool}
                "mandatory": data.get("mandatory", {}),  # {subject: code}
            }
        # 旧格式：扁平结构 {code: int}，兼容转换
        return {
            "targets": {k: int(v) for k, v in data.items()
                        if k in CONFIGURABLE_CODES and isinstance(v, (int, float))
                        and MIN_TARGET <= int(v) <= MAX_TARGET},
            "enabled": {},
            "mandatory": {},
        }
    except Exception:
        return {"targets": {}, "enabled": {}, "mandatory": {}}


def _setting_target(settings: dict, code: str) -> int | None:
    targets = settings.get("targets", settings) if isinstance(settings.get("targets"), dict) else settings
    val = targets.get(code)
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _is_task_enabled(settings: dict, code: str) -> bool:
    """检查任务是否启用（默认全部启用）"""
    enabled = settings.get("enabled", {})
    if not enabled:
        return True
    return enabled.get(code, True)


def _get_mandatory_code(settings: dict, subject: str) -> str | None:
    """获取家长设置的该学科强制任务 code（None 表示用默认值）"""
    mandatory = settings.get("mandatory", {})
    code = mandatory.get(subject)
    if code and code in CONFIGURABLE_CODES:
        return code
    return None


class SettingsRequest(BaseModel):
    user_id: str
    settings: dict = Field(default_factory=dict)


@router.get("/settings", summary="获取每日任务配置（目标+启用+强制/可选）")
def get_task_settings(user_id: str = Query(...), db: Session = Depends(get_db)):
    user = _load_settings(db, user_id)
    targets = user.get("targets", {})
    enabled_map = user.get("enabled", {})
    mandatory_map = user.get("mandatory", {})
    items = []
    all_tasks = list(MANDATORY_TASKS.values()) + OPTIONAL_POOL
    for code in CONFIGURABLE_CODES:
        item = next((t for t in all_tasks if t["code"] == code), None)
        if not item:
            continue
        subj = item.get("subject", "")
        if not subj:
            subj = next((s for s, t in MANDATORY_TASKS.items() if t["code"] == code), "")
        items.append({
            "code": code, "subject": subj, "title": item["title"],
            "default": item["target"], "target": targets.get(code, item["target"]),
            "enabled": enabled_map.get(code, True),
            "manual": item.get("manual", False),
        })
    current_mandatory = {}
    for subj in SUBJECTS:
        default_code = MANDATORY_TASKS[subj]["code"]
        current_mandatory[subj] = mandatory_map.get(subj, default_code)
    return {"items": items, "mandatory": current_mandatory}


@router.post("/settings", summary="保存每日任务配置（家长设置）")
def save_task_settings(req: SettingsRequest, db: Session = Depends(get_db)):
    if not isinstance(req.settings, dict):
        raise HTTPException(400, "settings 必须为对象")

    existing = _load_settings(db, req.user_id)
    new_targets = dict(existing.get("targets", {}))
    new_enabled = dict(existing.get("enabled", {}))
    new_mandatory = dict(existing.get("mandatory", {}))

    if "targets" in req.settings or "enabled" in req.settings or "mandatory" in req.settings:
        # 新格式
        if "targets" in req.settings and isinstance(req.settings["targets"], dict):
            for code, val in req.settings["targets"].items():
                if code not in CONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                try:
                    v = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{code} 的目标数量必须是整数")
                if not MIN_TARGET <= v <= MAX_TARGET:
                    raise HTTPException(400, f"{code} 的目标数量需在 {MIN_TARGET}-{MAX_TARGET} 之间")
                new_targets[code] = v
        if "enabled" in req.settings and isinstance(req.settings["enabled"], dict):
            for code, val in req.settings["enabled"].items():
                if code not in CONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                new_enabled[code] = bool(val)
        if "mandatory" in req.settings and isinstance(req.settings["mandatory"], dict):
            for subj, code in req.settings["mandatory"].items():
                if subj not in SUBJECTS:
                    raise HTTPException(400, f"不支持的学科: {subj}")
                if code not in CONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                new_mandatory[subj] = code
    else:
        # 旧格式兼容：{code: int}
        for code, val in req.settings.items():
            if code not in CONFIGURABLE_CODES:
                raise HTTPException(400, f"不支持的任务类型: {code}")
            try:
                v = int(val)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{code} 的目标数量必须是整数")
            if not MIN_TARGET <= v <= MAX_TARGET:
                raise HTTPException(400, f"{code} 的目标数量需在 {MIN_TARGET}-{MAX_TARGET} 之间")
            new_targets[code] = v

    clean = {"targets": new_targets, "enabled": new_enabled, "mandatory": new_mandatory}
    db.execute(text(
        "INSERT INTO parent_task_settings (user_id, settings_json, updated_at) "
        "VALUES (:u, :j, :t) ON CONFLICT(user_id) DO UPDATE SET settings_json=:j, updated_at=:t"),
        {"u": req.user_id, "j": json.dumps(clean), "t": datetime.now()})
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == req.user_id, DailyTask.task_date == today).all()
    for r in rows:
        if r.status != "done" and r.task_code in new_targets:
            r.target = new_targets[r.task_code]
    db.commit()
    return get_task_settings(req.user_id, db)


# ═══════════════ 进度追踪辅助 ═══════════════

def _today_start() -> datetime:
    return datetime.combine(date.today(), dtime.min)


def _today_attempts(db: Session, user_id: str, subject: str) -> int:
    return db.query(ExamAttempt).join(ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
        ExamAttempt.score >= TASK_PASS_SCORE, ExamAttempt.created_at >= _today_start(),
    ).count()


def _today_mastered(db: Session, user_id: str, subject: str) -> int:
    return db.query(WrongRecord).join(Question, WrongRecord.question_id == Question.id).filter(
        WrongRecord.user_id == user_id, Question.subject == subject,
        WrongRecord.mastered_at != None, WrongRecord.mastered_at >= _today_start(),
    ).count()


def _today_challenge_count(db: Session, user_id: str, kind: str) -> int:
    """今天某类挑战赛的完成次数"""
    from ..models.sprint4 import ChallengeRecord
    return db.query(ChallengeRecord).filter(
        ChallengeRecord.user_id == user_id,
        ChallengeRecord.kind == kind,
        ChallengeRecord.created_at >= _today_start(),
    ).count()


def _today_dictation_words(db: Session, user_id: str) -> int:
    """今天听写的单词数（从 VocabDailyLog 的 words_reviewed 字段近似）"""
    log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id, VocabDailyLog.learn_date == date.today()
    ).first()
    return (log.words_reviewed or 0) if log else 0


def _today_dictation_texts(db: Session, user_id: str) -> int:
    """今天默写的古诗文数（从 ClassicalDailyLog 近似）"""
    log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id, ClassicalDailyLog.learn_date == date.today()
    ).first()
    return (log.texts_reviewed or 0) if log else 0


def _task_progress(db: Session, user_id: str, subj: str, code: str, target: int) -> int:
    """根据真实学习数据计算任务进度（封顶为目标值）"""
    # 强制任务
    if code == "math_exam":
        return min(target, _today_attempts(db, user_id, "数学"))
    if code == "chi_classical":
        log = db.query(ClassicalDailyLog).filter(
            ClassicalDailyLog.user_id == user_id, ClassicalDailyLog.learn_date == date.today()
        ).first()
        if not log:
            return 0
        learned = log.texts_learned or 0
        reviewed = log.texts_reviewed or 0
        # 必须新背+复习都完成才算进度
        if learned > 0 and reviewed > 0:
            return min(target, learned + reviewed)
        return 0
    if code == "eng_vocab":
        log = db.query(VocabDailyLog).filter(
            VocabDailyLog.user_id == user_id, VocabDailyLog.learn_date == date.today()
        ).first()
        if not log:
            return 0
        new_learned = log.new_words_learned or 0
        reviewed = log.words_reviewed or 0
        # 必须新学+复习都完成才算进度（任一为0则进度为0）
        if new_learned > 0 and reviewed > 0:
            return min(target, new_learned + reviewed)
        return 0
    # 可选任务
    if code == "math_fix":
        return min(target, _today_mastered(db, user_id, "数学"))
    if code == "chi_exam":
        return min(target, _today_attempts(db, user_id, "语文"))
    if code == "eng_exam":
        return min(target, _today_attempts(db, user_id, "英语"))
    if code == "math_challenge":
        return min(target, _today_challenge_count(db, user_id, "math"))
    if code == "eng_challenge":
        return min(target, _today_challenge_count(db, user_id, "word"))
    if code == "eng_dictation":
        return min(target, _today_dictation_words(db, user_id))
    if code == "chi_dictation":
        return min(target, _today_dictation_texts(db, user_id))
    return 0


# ═══════════════ 任务行生成 ═══════════════

def _ensure_today_rows(db: Session, user_id: str) -> dict:
    """确保今天任务行存在（强制 + 可选，受家长配置影响）"""
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today).all()
    by_type = {}
    for r in rows:
        tt = getattr(r, 'task_type', 'mandatory') or 'mandatory'
        by_type.setdefault(tt, {})[r.subject] = r

    settings = _load_settings(db, user_id)
    changed = False

    # 强制任务：每科 1 条（使用家长设置的强制任务 code）
    mandatory = by_type.get("mandatory", {})
    for subj in SUBJECTS:
        if subj not in mandatory:
            # 家长可覆盖每科的强制任务
            override_code = _get_mandatory_code(settings, subj)
            if override_code:
                # 从 OPTIONAL_POOL 找任务定义
                t = next((t for t in OPTIONAL_POOL if t["code"] == override_code), None)
                if not t:
                    t = MANDATORY_TASKS[subj]
            else:
                t = MANDATORY_TASKS[subj]
            row = DailyTask(
                user_id=user_id, task_date=today, subject=subj,
                task_code=t["code"], title=t["title"],
                target=_setting_target(settings, t["code"]) or t["target"],
                progress=0, status="pending", manual=t.get("manual", False),
                task_type="mandatory",
            )
            db.add(row)
            changed = True

    # 可选任务：系统生成 3 条（过滤掉已禁用的任务）
    optional = by_type.get("optional", {})
    if not optional:
        picked = _pick_daily_optional(user_id, today, settings)
        for i, t in enumerate(picked):
            subj = t["subject"]
            row = DailyTask(
                user_id=user_id, task_date=today, subject=subj,
                task_code=t["code"], title=t["title"],
                target=_setting_target(settings, t["code"]) or t["target"],
                progress=0, status="pending", manual=t.get("manual", False),
                task_type="optional",
            )
            db.add(row)
            changed = True

    if changed:
        db.commit()

    # 重新查询返回
    all_rows = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == today).all()
    return all_rows


# ═══════════════ 全勤 & 连续天数（含补签卡） ═══════════════

def _is_full_day(db: Session, user_id: str, d: date) -> bool:
    """判断某天是否全勤（强制任务全部 done）"""
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == user_id, DailyTask.task_date == d,
        DailyTask.task_type == "mandatory",
    ).all()
    return len(rows) >= len(SUBJECTS) and all(r.status == "done" for r in rows)


def _has_makeup_card(db: Session, user_id: str, d: date) -> bool:
    """判断某天是否已使用补签卡"""
    return db.query(MakeupUsageLog).filter(
        MakeupUsageLog.user_id == user_id, MakeupUsageLog.target_date == d
    ).count() > 0


def _streak(db: Session, user_id: str) -> int:
    """连续全勤天数（含补签卡补签的日子）"""
    today = date.today()
    streak = 0
    d = today if _is_full_day(db, user_id, today) else today - timedelta(days=1)
    while _is_full_day(db, user_id, d) or _has_makeup_card(db, user_id, d):
        streak += 1
        d -= timedelta(days=1)
        if streak > 3660:
            break
    return streak


# ═══════════════ 补签卡 ═══════════════

def _get_makeup_balance(db: Session, user_id: str) -> int:
    card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
    return (card.balance if card else 0)


def _grant_makeup_card(db: Session, user_id: str):
    """完成全部可选任务 → 获得 1 张补签卡"""
    card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
    if not card:
        card = MakeupCard(user_id=user_id, balance=0, total_earned=0, total_used=0)
        db.add(card)
        db.flush()
    card.balance += 1
    card.total_earned += 1
    db.commit()


@router.post("/makeup/use", summary="使用补签卡补签某天")
def use_makeup_card(
    req: dict = Body(...),
    db: Session = Depends(get_db),
):
    user_id = req.get("user_id", "").strip()
    target = req.get("target_date", "")
    if not user_id or not target:
        raise HTTPException(400, "需要 user_id 和 target_date")
    try:
        d = date.fromisoformat(target)
    except ValueError:
        raise HTTPException(400, "日期格式错误，用 YYYY-MM-DD")
    if d >= date.today():
        raise HTTPException(400, "只能补签过去的日期")
    balance = _get_makeup_balance(db, user_id)
    if balance <= 0:
        raise HTTPException(400, "没有可用的补签卡")
    if _has_makeup_card(db, user_id, d):
        raise HTTPException(400, "该日期已补签过")
    log = MakeupUsageLog(user_id=user_id, target_date=d)
    db.add(log)
    card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
    card.balance -= 1
    card.total_used += 1
    db.commit()
    return {"balance": card.balance, "target_date": target, "message": "补签成功！当天算全勤"}


@router.get("/makeup/balance", summary="查询补签卡余额")
def get_makeup_balance(user_id: str = Query(...), db: Session = Depends(get_db)):
    return {"user_id": user_id, "balance": _get_makeup_balance(db, user_id)}


# ═══════════════ 构建返回数据 ═══════════════

def _build_payload(db: Session, user_id: str) -> dict:
    """刷新今日任务：计算进度、自动完成、汇总全勤"""
    all_rows = _ensure_today_rows(db, user_id)
    settings = _load_settings(db, user_id)

    mandatory_rows = []
    optional_rows = []
    for r in all_rows:
        tt = getattr(r, 'task_type', 'mandatory') or 'mandatory'
        if tt == "mandatory":
            mandatory_rows.append(r)
        else:
            optional_rows.append(r)

    # 计算进度 & 自动完成
    for row in all_rows:
        if row.status == "done":
            continue
        if not row.manual:
            prog = _task_progress(db, user_id, row.subject, row.task_code, row.target)
            row.progress = prog
            if prog >= row.target:
                row.status = "done"
                try:
                    from .rewards import inc_active_wish_progress
                    inc_active_wish_progress(db, user_id, 1)
                except Exception:
                    pass
    db.commit()

    # 检查 optional_streak 类型许愿进度
    try:
        from .rewards import check_wish_optional_streak
        check_wish_optional_streak(db, user_id)
    except Exception:
        pass

    # 检查可选任务是否全部完成 → 发补签卡
    optional_done = all(r.status == "done" for r in optional_rows) if optional_rows else False
    if optional_done and optional_rows:
        # 检查今天是否已经发过（避免重复发放）
        today_str = str(date.today())
        card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
        if card and getattr(card, 'updated_at', None):
            last_grant = str(card.updated_at.date()) if card.updated_at else ""
            if last_grant != today_str:
                _grant_makeup_card(db, user_id)
        elif not card:
            _grant_makeup_card(db, user_id)

    # 全勤日 → 卡券累计
    mandatory_all_done = all(r.status == "done" for r in mandatory_rows) if mandatory_rows else False
    if mandatory_all_done:
        try:
            from .rewards import sync_coupon_progress
            sync_coupon_progress(db, user_id)
        except Exception:
            pass

    # 组装返回
    all_tasks_list = list(MANDATORY_TASKS.values()) + OPTIONAL_POOL
    tasks = []
    for r in sorted(all_rows, key=lambda x: (0 if getattr(x, 'task_type', 'mandatory') == 'mandatory' else 1, x.subject)):
        tt = getattr(r, 'task_type', 'mandatory') or 'mandatory'
        cur = next((t for t in all_tasks_list if t["code"] == r.task_code), None)
        if not cur:
            continue
        tasks.append({
            "subject": r.subject,
            "task_code": r.task_code,
            "title": _display_title(cur["title"], r.target, cur["target"]),
            "target": r.target,
            "progress": r.progress,
            "status": r.status,
            "manual": r.manual,
            "mandatory": tt == "mandatory",
            "ico": cur["ico"],
            "desc": cur["desc"],
        })

    mandatory_done = sum(1 for r in mandatory_rows if r.status == "done")
    optional_done_count = sum(1 for r in optional_rows if r.status == "done")
    return {
        "date": str(date.today()),
        "tasks": tasks,
        "mandatory_done": mandatory_done,
        "mandatory_total": len(SUBJECTS),
        "optional_done": optional_done_count,
        "optional_total": len(optional_rows),
        "done_count": mandatory_done,
        "total": len(SUBJECTS),
        "streak_days": _streak(db, user_id),
        "makeup_cards": _get_makeup_balance(db, user_id),
    }


@router.get("/daily", summary="今日任务（3强制+3可选）")
def get_daily(user_id: str = Query(...), db: Session = Depends(get_db)):
    return _build_payload(db, user_id)


class ClaimRequest(BaseModel):
    user_id: str
    subject: str


@router.post("/daily/claim", summary="手动确认完成任务")
def claim_task(req: ClaimRequest, db: Session = Depends(get_db)):
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == req.user_id, DailyTask.task_date == today,
        DailyTask.subject == req.subject, DailyTask.task_type == "mandatory",
    ).all()
    row = rows[0] if rows else None
    if not row:
        raise HTTPException(404, "未找到任务")
    if not row.manual:
        raise HTTPException(400, "该任务由学习数据自动判定，无需手动确认")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    row.progress = row.target
    row.status = "done"
    try:
        from .rewards import inc_active_wish_progress
        inc_active_wish_progress(db, req.user_id, 1)
    except Exception:
        pass
    try:
        from .pet import _grant_coins
        _grant_coins(db, req.user_id, 5, "完成任务")
    except Exception:
        pass
    db.commit()
    return _build_payload(db, req.user_id)
