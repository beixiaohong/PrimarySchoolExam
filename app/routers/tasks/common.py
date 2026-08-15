"""每日任务路由包：常量与共享辅助函数（内部使用，无路由）"""
import hashlib
import json
import logging
import re
from datetime import date, datetime, time as dtime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily_task import DailyTask
from app.models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from app.models.vocab import VocabDailyLog
from app.models.classical import ClassicalDailyLog
from app.models.study_error import StudyError
from app.models.makeup_card import MakeupCard, MakeupUsageLog
from app.models.parent_custom_task import ParentCustomTask

logger = logging.getLogger(__name__)

SUBJECTS = ["数学", "语文", "英语"]

# ═══════════════ 强制任务（每科固定 1 条，不可更换） ═══════════════

MANDATORY_TASKS = {
    "数学": {"code": "math_exam", "title": "完成数学练习", "target": 2, "manual": False,
             "ico": "🧮", "desc": "刷题中心完成数学试卷（套数由家长配置，每套正确率需 ≥70%；须做不同的新卷，重复刷同一张不计入）"},
    "语文": {"code": "chi_classical", "title": "背诵古诗文（新背+复习）", "target": 1, "manual": False,
             "ico": "📜", "desc": "背诵中心完成今日新背内容，并完成当日到期复习额度（或全部到期复习亦可）"},
    "英语": {"code": "eng_vocab", "title": "学单词（新学+复习）", "target": 5, "manual": False,
             "ico": "🔤", "desc": "背单词模块完成今日新学单词，并完成当日到期复习额度（或全部到期复习亦可）"},
}

# ═══════════════ 可选任务池（系统每日随机抽 3 条） ═══════════════

OPTIONAL_POOL = [
    # 数学
    {"code": "math_fix", "title": "订正 10 道数学错题", "target": 10, "manual": False,
     "ico": "📕", "desc": "错题本重做或标记已掌握", "subject": "数学"},
    {"code": "math_teach", "title": "给家长讲 1 道题", "target": 1, "manual": True,
     "ico": "🎓", "desc": "挑一道今天的题讲给家长听", "subject": "数学"},
    {"code": "math_challenge", "title": "数学 60 秒挑战赛 1 次", "target": 1, "manual": False,
     "ico": "⚡", "desc": "限时挑战赛，60 秒内尽可能多答对；本场正确率需 ≥ 80% 才算完成", "subject": "数学"},
    {"code": "math_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成数学同步练习后，找家长确认", "subject": "数学"},
    # 语文
    {"code": "chi_exam", "title": "完成 1 套语文练习", "target": 1, "manual": False,
     "ico": "🖋️", "desc": "刷题中心做一套语文试卷（须做不同的新卷，重复刷同一张不计入）", "subject": "语文"},
    {"code": "chi_read", "title": "朗读课文 5 分钟", "target": 5, "manual": True,
     "ico": "🎙️", "desc": "大声朗读课文或古诗，完成后由家长确认", "subject": "语文"},
    {"code": "chi_dictation", "title": "默写 3 首古诗", "target": 3, "manual": False,
     "ico": "✍️", "desc": "在背诵中心完成古诗文默写", "subject": "语文"},
    {"code": "chi_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成语文同步练习后，找家长确认", "subject": "语文"},
    # 英语
    {"code": "eng_exam", "title": "完成 1 套英语练习", "target": 1, "manual": False,
     "ico": "📝", "desc": "刷题中心做一套英语试卷（须做不同的新卷，重复刷同一张不计入）", "subject": "英语"},
    {"code": "eng_dictation", "title": "听写 10 个单词", "target": 10, "manual": False,
     "ico": "👂", "desc": "在听写磨耳朵完成单词听写", "subject": "英语"},
    {"code": "eng_challenge", "title": "英语 60 秒挑战赛 1 次", "target": 1, "manual": False,
     "ico": "⚡", "desc": "限时挑战赛，60 秒内尽可能多答对；本场正确率需 ≥ 80% 才算完成", "subject": "英语"},
    {"code": "eng_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成英语同步练习后，找家长确认", "subject": "英语"},
]

# 家长可配置目标数量的任务（背诵类固定「全量完成」语义，不可配置目标数）
_UNCONFIGURABLE_CODES = {"chi_classical", "eng_vocab"}
CONFIGURABLE_CODES = [t["code"] for t in [
    MANDATORY_TASKS["数学"], MANDATORY_TASKS["语文"], MANDATORY_TASKS["英语"],
]] + [t["code"] for t in OPTIONAL_POOL]
# 去重并排除不可配置项
CONFIGURABLE_CODES = [c for c in dict.fromkeys(CONFIGURABLE_CODES)
                      if c not in _UNCONFIGURABLE_CODES]

MIN_TARGET, MAX_TARGET = 1, 50
# 按任务单独设置的目标下限（默认为空：数值由家长配置，系统只提供能力）
CODE_MIN_TARGET = {}

# 家长可配置的背诵额度（quotas）：{键: (最小值, 最大值, 默认值)}
# 语义为「每轮新学数量」：不限制每日轮数，学完一轮可立即开下一轮
QUOTA_KEYS = {
    "daily_new_words": (1, 100, 20),   # 每轮新学单词数
    "daily_new_texts": (1, 50, 5),     # 每轮新背古诗文数
    "daily_review_words": (1, 100, 10),  # 每天需复习的单词数（到期复习的每日额度，积压可逐日消化）
    "daily_review_texts": (1, 50, 5),   # 每天需复习的古诗文数
}

# 练习类任务的完成门槛（分数≥70才算完成）
TASK_PASS_SCORE = 70


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
        # 新格式：嵌套结构 {"targets": {...}, "enabled": {...}, "mandatory": {...}, "quotas": {...}}
        if "targets" in data and isinstance(data["targets"], dict):
            targets = {k: int(v) for k, v in data["targets"].items()
                       if (k in CONFIGURABLE_CODES or k in _UNCONFIGURABLE_CODES)
                       and isinstance(v, (int, float))
                       and MIN_TARGET <= int(v) <= MAX_TARGET}
            return {
                "targets": targets,
                "enabled": data.get("enabled", {}),  # {code: bool}
                "mandatory": _normalize_mandatory(data.get("mandatory", {})),  # {subject: [追加codes]}
                "quotas": data.get("quotas", {}),  # {daily_new_words: int, ...}
                "optional": [c for c in data.get("optional", [])  # 家长添加的可选任务 code 列表
                             if isinstance(c, str) and c in CONFIGURABLE_CODES],
            }
        # 旧格式：扁平结构 {code: int}，兼容转换
        return {
            "targets": {k: int(v) for k, v in data.items()
                        if (k in CONFIGURABLE_CODES or k in _UNCONFIGURABLE_CODES)
                        and isinstance(v, (int, float))
                        and MIN_TARGET <= int(v) <= MAX_TARGET},
            "enabled": {},
            "mandatory": {},
            "quotas": {},
            "optional": [],
        }
    except Exception:
        return {"targets": {}, "enabled": {}, "mandatory": {}, "quotas": {}, "optional": []}


def _load_study_flags(db: Session, user_id: str) -> dict:
    """读取 settings_json 原始内容，供学习开关使用

    顶层字段：include_next(预习下学期)、sync_mode(课堂同步)、xsc_bridge(小升初衔接)
    """
    row = db.execute(
        text("SELECT settings_json FROM parent_task_settings WHERE user_id=:u"),
        {"u": user_id}).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row[0] or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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


def _normalize_mandatory(raw) -> dict:
    """将存储的 mandatory 归一化为 {subject: [追加codes]}（兼容旧格式单 code 字符串）"""
    out = {}
    if not isinstance(raw, dict):
        return out
    for subj, val in raw.items():
        if subj not in SUBJECTS:
            continue
        codes = [val] if isinstance(val, str) else (val if isinstance(val, list) else [])
        cleaned = []
        for c in codes:
            if isinstance(c, str) and c and c not in cleaned:
                cleaned.append(c)
        out[subj] = cleaned
    return out


def _get_mandatory_codes(settings: dict, subject: str) -> list:
    """该科强制任务 code 列表：默认任务固定保留 + 家长追加项（去重）"""
    codes = [MANDATORY_TASKS[subject]["code"]]
    for c in settings.get("mandatory", {}).get(subject, []):
        if c not in codes:
            codes.append(c)
    return codes


def _task_def_by_code(code: str) -> dict | None:
    """按 code 查任务定义（含强制任务，补全 subject 字段）"""
    for subj, t in MANDATORY_TASKS.items():
        if t["code"] == code:
            return {**t, "subject": subj}
    for t in OPTIONAL_POOL:
        if t["code"] == code:
            return t
    return None


def _bounded_target(code: str, v: int) -> int:
    """目标数上下限校验：全局 1-50，个别任务可另设下限"""
    lo = max(MIN_TARGET, CODE_MIN_TARGET.get(code, MIN_TARGET))
    if not lo <= v <= MAX_TARGET:
        raise HTTPException(400, f"{code} 的目标数量需在 {lo}-{MAX_TARGET} 之间")
    return v


def get_daily_quota(db: Session, user_id: str, key: str) -> int:
    """读家长配置的每日额度（quotas），未配置时返回默认值"""
    lo, hi, default = QUOTA_KEYS[key]
    settings = _load_settings(db, user_id)
    try:
        v = int(settings.get("quotas", {}).get(key, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


# 学习开关（settings_json 顶层 bool）：预习下学期 / 课堂同步 / 小升初衔接
STUDY_FLAG_KEYS = ("include_next", "sync_mode", "xsc_bridge")


# ═══════════════ 进度追踪辅助 ═══════════════

def _today_start() -> datetime:
    return datetime.combine(date.today(), dtime.min)


def _today_new_attempts(db: Session, user_id: str, subject: str) -> int:
    """今日达标、且以往从未做过的卷子数（防反复刷同一张卷子凑每日任务）

    判定标准：今日分数达标的卷子中，exam_id 在「今天之前」不存在该用户的任何做题记录。
    即同一份卷子只有第一次做才算数，之后每天重做都不再计入进度——必须做新卷子才能完成。
    """
    today_start = _today_start()
    # 今日达标 attempt 涉及的卷子（去重）
    todays = db.query(func.distinct(ExamAttempt.exam_id)).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
        ExamAttempt.score >= TASK_PASS_SCORE, ExamAttempt.created_at >= today_start,
    ).all()
    new_ids = {r[0] for r in todays}
    if not new_ids:
        return 0
    # 这些卷子中，今天之前该用户是否已做过（任何 attempt，不限分数 → 接触过即不算新）
    prev = db.query(func.distinct(ExamAttempt.exam_id)).join(
        ExamRecord, ExamAttempt.exam_id == ExamRecord.id).filter(
        ExamAttempt.user_id == user_id, ExamRecord.subject == subject,
        ExamAttempt.created_at < today_start,
        ExamAttempt.exam_id.in_(new_ids),
    ).all()
    prev_ids = {r[0] for r in prev}
    return len(new_ids - prev_ids)


def _today_mastered(db: Session, user_id: str, subject: str) -> int:
    """今日通过重做答对而掌握的错题数（防刷：手动标记已掌握不计入，需正确答对 correct_streak>0）"""
    return db.query(WrongRecord).join(Question, WrongRecord.question_id == Question.id).filter(
        WrongRecord.user_id == user_id, Question.subject == subject,
        WrongRecord.mastered_at != None, WrongRecord.mastered_at >= _today_start(),
        WrongRecord.correct_streak > 0,
    ).count()


def _today_challenge_count(db: Session, user_id: str, kind: str) -> int:
    """今天某类挑战赛中「通过（正确率 ≥ 80%）」的次数。

    需求：60 秒挑战赛需通过率 80% 以上才算完成。故只统计
    total>0 且 correct/total ≥ 0.8 的记录，低分挑战不计入每日任务进度。
    """
    from app.models.sprint4 import ChallengeRecord
    rows = db.query(ChallengeRecord).filter(
        ChallengeRecord.user_id == user_id,
        ChallengeRecord.kind == kind,
        ChallengeRecord.created_at >= _today_start(),
    ).all()
    return sum(
        1 for r in rows
        # 通过判定：正确率 ≥ 80%（correct/total >= 0.8 等价于 correct*5 >= total*4）
        if r.total and r.total > 0 and r.correct * 5 >= r.total * 4
    )


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


def _user_grade(db: Session, user_id: str) -> int:
    """取用户年级（背诵任务按年级圈定词库/篇目）"""
    from app.models.user import User
    u = db.query(User).filter_by(user_id=user_id).first()
    return (u.grade if u and u.grade else 6)


def _vocab_all_done(db: Session, user_id: str) -> tuple:
    """英语单词「全量完成」判定：今日新学全部完成 且 当日复习达标（或清空积压）。

    返回 (done, new_done, review_done, learned_today, reviewed_today)。
    - 新学完成：新学额度用完（今日新学数达标或词库已无可学新词）
    - 复习完成：当天已复习数达到每日复习额度，或已无剩余到期复习词（积压清空）。
      用「每日复习额度」替代「清空全部积压」，避免初期积压单词导致任务永远无法完成。
    """
    from app.models.word import Word, WordBook
    from app.models.vocab import VocabProgress
    today = date.today()
    grade = _user_grade(db, user_id)
    book_ids = [b.id for b in db.query(WordBook).filter(WordBook.grade == grade).all()]
    if not book_ids:
        return True, True, True, 0, 0  # 无词库视为完成，不阻塞全勤
    word_q = db.query(Word.id).filter(Word.book_id.in_(book_ids))

    # 到期复习剩余数（复习后 next_review_date 均 > 今日）
    review_left = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "learning",
        VocabProgress.next_review_date <= today,
        VocabProgress.word_id.in_(word_q),
    ).count()

    log = db.query(VocabDailyLog).filter(
        VocabDailyLog.user_id == user_id, VocabDailyLog.learn_date == today).first()
    learned_today = (log.new_words_learned or 0) if log else 0
    reviewed_today = (log.words_reviewed or 0) if log else 0

    if learned_today >= get_daily_quota(db, user_id, "daily_new_words"):
        new_done = True
    else:
        # 词库中是否还有未学新词（无新词可学也视为完成）
        learned_ids = db.query(VocabProgress.word_id).filter(
            VocabProgress.user_id == user_id).subquery()
        unlearned = db.query(Word.id).filter(
            Word.book_id.in_(book_ids), ~Word.id.in_(db.query(learned_ids))).count()
        new_done = unlearned == 0

    review_quota = get_daily_quota(db, user_id, "daily_review_words")
    # 复习完成：无固定门槛（清空积压）或当天已复习达到每日额度
    review_done = (review_left == 0) or (reviewed_today >= review_quota)
    return (new_done and review_done), new_done, review_done, learned_today, reviewed_today


def _classical_all_done(db: Session, user_id: str) -> tuple:
    """古诗文「全量完成」判定：今日新背全部完成 且 当日复习达标（或清空积压）。

    返回 (done, new_done, review_done, learned_today, reviewed_today)。
    复习完成用「每日复习额度」替代「清空全部积压」，避免初期积压篇目导致任务永远无法完成。
    """
    from app.models.classical import ClassicalText, ClassicalProgress
    today = date.today()
    grade = _user_grade(db, user_id)

    review_left = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "learning",
        ClassicalProgress.next_review_date <= today,
    ).count()

    log = db.query(ClassicalDailyLog).filter(
        ClassicalDailyLog.user_id == user_id, ClassicalDailyLog.learn_date == today).first()
    learned_today = (log.texts_learned or 0) if log else 0
    reviewed_today = (log.texts_reviewed or 0) if log else 0

    if learned_today >= get_daily_quota(db, user_id, "daily_new_texts"):
        new_done = True
    else:
        learned_ids = db.query(ClassicalProgress.text_id).filter(
            ClassicalProgress.user_id == user_id).subquery()
        unlearned = db.query(ClassicalText.id).filter(
            ClassicalText.grade <= grade,
            ~ClassicalText.id.in_(db.query(learned_ids))).count()
        new_done = unlearned == 0

    review_quota = get_daily_quota(db, user_id, "daily_review_texts")
    # 复习完成：无固定门槛（清空积压）或当天已复习达到每日额度
    review_done = (review_left == 0) or (reviewed_today >= review_quota)
    return (new_done and review_done), new_done, review_done, learned_today, reviewed_today


def _task_progress(db: Session, user_id: str, subj: str, code: str, target: int) -> int:
    """根据真实学习数据计算任务进度（封顶为目标值）"""
    # 强制任务
    if code == "math_exam":
        return min(target, _today_new_attempts(db, user_id, "数学"))
    if code == "chi_classical":
        done, _, _, learned, reviewed = _classical_all_done(db, user_id)
        if done:
            return target
        # 未全部完成：展示进度但永不达标（新背+复习必须全部完成）
        return min(target - 1, learned + reviewed)
    if code == "eng_vocab":
        done, _, _, learned, reviewed = _vocab_all_done(db, user_id)
        if done:
            return target
        return min(target - 1, learned + reviewed)
    # 可选任务
    if code == "math_fix":
        return min(target, _today_mastered(db, user_id, "数学"))
    if code == "chi_exam":
        return min(target, _today_new_attempts(db, user_id, "语文"))
    if code == "eng_exam":
        return min(target, _today_new_attempts(db, user_id, "英语"))
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
    # 唯一键为 user_id+task_date+task_code（不含 task_type）：
    # 记录今日已有/本次新增的任务 code，避免同 code 重复插入撞唯一索引
    existing_codes = {r.task_code for r in rows}

    # 强制任务：默认每科 1 条 + 家长追加项（每条 code 一行）
    for subj in SUBJECTS:
        for code in _get_mandatory_codes(settings, subj):
            if code in existing_codes:
                continue  # 今日已有该 code 行（含与可选配置重叠），不重复生成
            t = _task_def_by_code(code) or MANDATORY_TASKS[subj]
            row = DailyTask(
                user_id=user_id, task_date=today, subject=subj,
                task_code=t["code"], title=t["title"],
                target=_setting_target(settings, t["code"]) or t["target"],
                progress=0, status="pending", manual=t.get("manual", False),
                task_type="mandatory",
            )
            db.add(row)
            existing_codes.add(t["code"])
            changed = True

    # 可选任务：家长配置的全部生成（今日缺哪条补哪条），未配置时系统随机抽 3 条（过滤已禁用）
    picked = []
    for c in settings.get("optional", []):
        t = _task_def_by_code(c)
        if t and _is_task_enabled(settings, c):
            picked.append(t)
    if not picked and not by_type.get("optional"):
        picked = _pick_daily_optional(user_id, today, settings)
    for t in picked:
        if t["code"] in existing_codes:
            continue  # 今日已有该任务行（含强制/已完成），不重复生成
        row = DailyTask(
            user_id=user_id, task_date=today, subject=t["subject"],
            task_code=t["code"], title=t["title"],
            target=_setting_target(settings, t["code"]) or t["target"],
            progress=0, status="pending", manual=t.get("manual", False),
            task_type="optional",
        )
        db.add(row)
        existing_codes.add(t["code"])
        changed = True

    # 家长自定义任务（激活的，按 task_type 注入强制/可选区，手动确认）
    for c in db.query(ParentCustomTask).filter(
            ParentCustomTask.user_id == user_id,
            ParentCustomTask.active == True).order_by(
            ParentCustomTask.task_type, ParentCustomTask.sort_order, ParentCustomTask.id).all():
        code = "custom:%d" % c.id
        if code in existing_codes:
            continue  # 今日已有该自定义任务行，不重复生成
        row = DailyTask(
            user_id=user_id, task_date=today, subject=c.subject or "其他",
            task_code=code, title=(c.title or "自定义任务")[:100],
            target=max(1, int(c.target or 1)), progress=0, status="pending",
            manual=True, task_type=c.task_type,
        )
        db.add(row)
        existing_codes.add(code)
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
    """判断某天是否已使用补签卡且已生效（仅 confirmed 计入全勤/连续天数）"""
    return db.query(MakeupUsageLog).filter(
        MakeupUsageLog.user_id == user_id,
        MakeupUsageLog.target_date == d,
        MakeupUsageLog.status == "confirmed",
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


def _grant_makeup_card(db: Session, user_id: str) -> bool:
    """完成全部可选任务 → 获得 1 张补签卡。

    原子发放：仅当 last_grant_date 非今天时才更新成功，
    并发请求（如登录后多次 /daily）不会重复发卡。返回是否发放成功。
    """
    today = date.today()
    card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
    if not card:
        db.add(MakeupCard(user_id=user_id, balance=0, total_earned=0, total_used=0))
        db.commit()
    n = db.query(MakeupCard).filter(
        MakeupCard.user_id == user_id,
        or_(MakeupCard.last_grant_date == None, MakeupCard.last_grant_date != today),
    ).update({
        "balance": MakeupCard.balance + 1,
        "total_earned": MakeupCard.total_earned + 1,
        "last_grant_date": today,
    }, synchronize_session=False)
    db.commit()
    return n > 0


# ═══════════════ 构建返回数据 ═══════════════

def _build_payload(db: Session, user_id: str) -> dict:
    """刷新今日任务：计算进度、自动完成、汇总全勤"""
    all_rows = _ensure_today_rows(db, user_id)
    settings = _load_settings(db, user_id)

    # 待确认补签（孩子发起的补签卡完成任务）的任务 id 集合，用于前端展示「待家长确认」
    pending_task_ids = {
        lid for (lid,) in db.query(MakeupUsageLog.task_id).filter(
            MakeupUsageLog.user_id == user_id,
            MakeupUsageLog.status == "pending",
            MakeupUsageLog.task_id.isnot(None),
        ).all()
    }

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
                # 心愿进度仅统计可选任务（强制任务不计入）
                if (getattr(row, 'task_type', 'mandatory') or 'mandatory') == "optional":
                    try:
                        from app.routers.rewards import inc_active_wish_progress
                        inc_active_wish_progress(db, user_id, 1)
                    except Exception:
                        pass
    db.commit()

    # 检查 optional_streak 类型许愿进度
    try:
        from app.routers.rewards import check_wish_optional_streak
        check_wish_optional_streak(db, user_id)
    except Exception:
        pass

    # 检查可选任务是否全部完成 → 发补签卡
    optional_done = all(r.status == "done" for r in optional_rows) if optional_rows else False
    if optional_done and optional_rows:
        # 检查今天是否已经发过（用专用字段 last_grant_date，避免 updated_at 误判）
        today_str = str(date.today())
        card = db.query(MakeupCard).filter(MakeupCard.user_id == user_id).first()
        last_grant = str(card.last_grant_date) if (card and getattr(card, "last_grant_date", None)) else ""
        if last_grant != today_str:
            _grant_makeup_card(db, user_id)

    # 全勤日 → 卡券累计
    mandatory_all_done = all(r.status == "done" for r in mandatory_rows) if mandatory_rows else False
    if mandatory_all_done:
        try:
            from app.routers.rewards import sync_coupon_progress
            sync_coupon_progress(db, user_id)
        except Exception:
            pass

    # 组装返回
    all_tasks_list = list(MANDATORY_TASKS.values()) + OPTIONAL_POOL
    tasks = []
    for r in sorted(all_rows, key=lambda x: (0 if getattr(x, 'task_type', 'mandatory') == 'mandatory' else 1, x.subject)):
        tt = getattr(r, 'task_type', 'mandatory') or 'mandatory'
        cur = next((t for t in all_tasks_list if t["code"] == r.task_code), None)
        # 家长自定义任务：task_code 以 custom: 开头，标题/学科已存于 DailyTask 行
        if r.task_code.startswith("custom:"):
            tasks.append({
                "id": r.id,
                "subject": r.subject,
                "task_code": r.task_code,
                "title": r.title,
                "target": r.target,
                "progress": r.progress,
                "status": r.status,
                "manual": r.manual,
                "mandatory": tt == "mandatory",
                "ico": "📌",
                "desc": "家长自定义任务，完成后由家长确认",
                "makeup_pending": (r.id in pending_task_ids),
            })
            continue
        if not cur:
            continue
        tasks.append({
            "id": r.id,
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
            "makeup_pending": (r.id in pending_task_ids),
        })

    mandatory_done = sum(1 for r in mandatory_rows if r.status == "done")
    optional_done_count = sum(1 for r in optional_rows if r.status == "done")
    return {
        "date": str(date.today()),
        "tasks": tasks,
        "mandatory_done": mandatory_done,
        "mandatory_total": len(mandatory_rows),
        "optional_done": optional_done_count,
        "optional_total": len(optional_rows),
        "done_count": mandatory_done,
        "total": len(SUBJECTS),
        "streak_days": _streak(db, user_id),
        "makeup_cards": _get_makeup_balance(db, user_id),
    }


__all__ = [
    "logger", "SUBJECTS", "MANDATORY_TASKS", "OPTIONAL_POOL",
    "_UNCONFIGURABLE_CODES", "CONFIGURABLE_CODES", "MIN_TARGET", "MAX_TARGET",
    "CODE_MIN_TARGET", "QUOTA_KEYS", "TASK_PASS_SCORE",
    "_pick_daily_optional", "_default_target", "_display_title",
    "_load_settings", "_load_study_flags", "_setting_target",
    "_is_task_enabled", "_normalize_mandatory", "_get_mandatory_codes",
    "_task_def_by_code", "_bounded_target", "get_daily_quota",
    "STUDY_FLAG_KEYS", "_today_start", "_today_new_attempts",
    "_today_mastered", "_today_challenge_count", "_today_dictation_words",
    "_today_dictation_texts", "_user_grade", "_vocab_all_done",
    "_classical_all_done", "_task_progress", "_ensure_today_rows",
    "_is_full_day", "_has_makeup_card", "_streak", "_get_makeup_balance",
    "_grant_makeup_card", "_build_payload",
]
