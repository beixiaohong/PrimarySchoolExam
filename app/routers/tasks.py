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

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.parent_guard import ensure_parent_pwd
from ..models.daily_task import DailyTask
from ..models.exam import ExamAttempt, ExamRecord, Question, WrongRecord
from ..models.vocab import VocabDailyLog
from ..models.classical import ClassicalDailyLog
from ..models.study_error import StudyError
from ..models.makeup_card import MakeupCard, MakeupUsageLog
from ..models.parent_custom_task import ParentCustomTask

logger = logging.getLogger(__name__)

router = APIRouter()

SUBJECTS = ["数学", "语文", "英语"]

# ═══════════════ 强制任务（每科固定 1 条，不可更换） ═══════════════

MANDATORY_TASKS = {
    "数学": {"code": "math_exam", "title": "完成数学练习", "target": 2, "manual": False,
             "ico": "🧮", "desc": "刷题中心完成数学试卷（套数由家长配置，每套正确率需 ≥70%；须做不同的新卷，重复刷同一张不计入）"},
    "语文": {"code": "chi_classical", "title": "背诵古诗文（新背+复习全部完成）", "target": 1, "manual": False,
             "ico": "📜", "desc": "背诵中心完成今日新背内容与全部到期复习"},
    "英语": {"code": "eng_vocab", "title": "学单词（新学+复习全部完成）", "target": 5, "manual": False,
             "ico": "🔤", "desc": "背单词模块完成今日新学单词与全部到期复习"},
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


class SettingsRequest(BaseModel):
    user_id: str
    settings: dict = Field(default_factory=dict)


@router.get("/settings", summary="获取每日任务配置（目标+启用+强制/可选）")
def get_task_settings(user_id: str = Query(...), db: Session = Depends(get_db)):
    """获取每日任务配置（目标数/启用状态/追加强制任务/背诵额度/可选任务/学习开关）。

    参数（Query）：user_id。
    返回：{items[{code,subject,title,default,target,enabled,manual}], mandatory{学科:[追加codes]},
          quotas{每日新学单词/古诗文数}, optional[家长添加的可选code], study_flags{include_next/sync_mode/xsc_bridge}}。
    副作用：无（只读）。无需家长密码。
    """
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
        # 返回家长追加的强制任务 code 列表（默认任务后端保证存在，不存配置）
        current_mandatory[subj] = [c for c in mandatory_map.get(subj, [])
                                   if isinstance(c, str)]
    quotas = {k: int(user.get("quotas", {}).get(k, d)) for k, (_, _, d) in QUOTA_KEYS.items()}
    # 背诵类任务不在可配置列表，但作为强制任务时仍需返回 target 供前端回显数量
    for code in _UNCONFIGURABLE_CODES:
        item = next((t for t in all_tasks if t["code"] == code), None)
        if not item:
            continue
        subj = next((s for s, t in MANDATORY_TASKS.items() if t["code"] == code), "")
        items.append({
            "code": code, "subject": subj, "title": item["title"],
            "default": item["target"], "target": targets.get(code, item["target"]),
            "enabled": True, "manual": item.get("manual", False),
        })
    return {"items": items, "mandatory": current_mandatory, "quotas": quotas,
            "optional": user.get("optional", []),
            "study_flags": {k: bool(_load_study_flags(db, user_id).get(k, False))
                            for k in STUDY_FLAG_KEYS}}


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


@router.post("/settings", summary="保存每日任务配置（家长设置，需家长密码）")
def save_task_settings(req: SettingsRequest, request: Request, db: Session = Depends(get_db)):
    """保存每日任务配置（家长权限，需家长密码 X-Parent-Pwd）。

    参数（Body）：user_id、settings{targets/enabled/mandatory/quotas/optional/学习开关}。
    请求头：必须携带 X-Parent-Pwd（ensure_parent_pwd，否则 403）——防止孩子自行调低目标/禁用任务。
    返回：重新返回 get_task_settings 结构。
    副作用：upsert parent_task_settings；同步刷新今日未完成任务的目标/启用/追加项；
            目标数夹到 MIN_TARGET(1)-MAX_TARGET(50)，背诵类不可禁用。
    需要家长密码。
    """
    if not isinstance(req.settings, dict):
        raise HTTPException(400, "settings 必须为对象")
    # 防刷：任务配置是家长权限，孩子不得自行调低目标/禁用任务
    ensure_parent_pwd(db, req.user_id, request)

    # 学习开关单独提取（bool，可独立提交）
    flag_updates = {k: bool(req.settings[k]) for k in STUDY_FLAG_KEYS if k in req.settings}
    _payload = {k: v for k, v in req.settings.items() if k not in STUDY_FLAG_KEYS}

    existing = _load_settings(db, req.user_id)
    new_targets = dict(existing.get("targets", {}))
    new_enabled = dict(existing.get("enabled", {}))
    new_mandatory = dict(existing.get("mandatory", {}))
    new_quotas = dict(existing.get("quotas", {}))
    new_optional = list(existing.get("optional", []))

    # 家长添加的可选任务（code 列表，独立字段，可与其它字段分开提交）
    if "optional" in _payload:
        if not isinstance(_payload["optional"], list):
            raise HTTPException(400, "optional 必须为数组")
        seen, opt = set(), []
        for code in _payload["optional"]:
            if not isinstance(code, str) or code not in CONFIGURABLE_CODES:
                raise HTTPException(400, f"不支持的任务类型: {code}")
            if code not in seen:
                seen.add(code)
                opt.append(code)
        new_optional = opt

    if "targets" in _payload or "enabled" in _payload or "mandatory" in _payload \
            or "quotas" in _payload or "optional" in _payload:
        # 新格式
        if "targets" in _payload and isinstance(_payload["targets"], dict):
            for code, val in _payload["targets"].items():
                # 背诵类也允许保存目标数（仅展示用，完成判定仍为全量背诵+复习）
                if code not in CONFIGURABLE_CODES and code not in _UNCONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                try:
                    v = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{code} 的目标数量必须是整数")
                new_targets[code] = _bounded_target(code, v)
        if "enabled" in _payload and isinstance(_payload["enabled"], dict):
            for code, val in _payload["enabled"].items():
                if code in _UNCONFIGURABLE_CODES:
                    continue  # 强制背诵类任务不允许禁用，静默忽略
                if code not in CONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                new_enabled[code] = bool(val)
        if "mandatory" in _payload and isinstance(_payload["mandatory"], dict):
            for subj, val in _payload["mandatory"].items():
                if subj not in SUBJECTS:
                    raise HTTPException(400, f"不支持的学科: {subj}")
                # 兼容旧格式单 code 字符串；只存追加项，默认强制任务后端保证存在
                codes = [val] if isinstance(val, str) else (val if isinstance(val, list) else [])
                extra = []
                for code in codes:
                    if code == MANDATORY_TASKS[subj]["code"]:
                        continue
                    t = _task_def_by_code(code)
                    if not t or t.get("subject") != subj:
                        raise HTTPException(400, f"不支持的任务类型: {code}")
                    if code not in extra:
                        extra.append(code)
                new_mandatory[subj] = extra
        # 每日额度（家长配置：新学单词数 / 新背古诗文数）
        if "quotas" in _payload and isinstance(_payload["quotas"], dict):
            for key, val in _payload["quotas"].items():
                if key not in QUOTA_KEYS:
                    raise HTTPException(400, f"不支持的额度类型: {key}")
                lo, hi, _ = QUOTA_KEYS[key]
                try:
                    v = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{key} 必须是整数")
                if not lo <= v <= hi:
                    raise HTTPException(400, f"{key} 需在 {lo}-{hi} 之间")
                new_quotas[key] = v
    elif _payload:
        # 旧格式兼容：{code: int}
        for code, val in _payload.items():
            if code not in CONFIGURABLE_CODES and code not in _UNCONFIGURABLE_CODES:
                raise HTTPException(400, f"不支持的任务类型: {code}")
            try:
                v = int(val)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{code} 的目标数量必须是整数")
            new_targets[code] = _bounded_target(code, v)

    clean = {"targets": new_targets, "enabled": new_enabled,
             "mandatory": new_mandatory, "quotas": new_quotas,
             "optional": new_optional}
    # 学习开关持久化（顶层字段；未提交的保持原值）
    flags = _load_study_flags(db, req.user_id)
    flags.update(flag_updates)
    for k in STUDY_FLAG_KEYS:
        if k in flags:
            clean[k] = bool(flags[k])
    # 可移植 upsert（MySQL 兼容，不用 ON CONFLICT）
    _params = {"u": req.user_id, "j": json.dumps(clean), "t": datetime.now()}
    exists = db.execute(text("SELECT 1 FROM parent_task_settings WHERE user_id=:u"),
                        {"u": req.user_id}).fetchone()
    if exists:
        db.execute(text("UPDATE parent_task_settings SET settings_json=:j, updated_at=:t WHERE user_id=:u"), _params)
    else:
        db.execute(text("INSERT INTO parent_task_settings (user_id, settings_json, updated_at) "
                        "VALUES (:u, :j, :t)"), _params)
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == req.user_id, DailyTask.task_date == today).all()
    for r in rows:
        if r.status != "done" and r.task_code in new_targets:
            r.target = new_targets[r.task_code]
    # 强制任务追加列表变更：删除今日未完成且已不在（默认+追加）列表中的强制行
    for r in rows:
        if getattr(r, "task_type", "") == "mandatory" and r.status != "done":
            valid = _get_mandatory_codes({"mandatory": new_mandatory}, r.subject)
            if r.task_code not in valid:
                db.delete(r)
    # 可选任务配置变更：删除今日未完成的可选行，下次 /daily 按新配置重新生成
    if new_optional != list(existing.get("optional", [])):
        for r in rows:
            if getattr(r, "task_type", "") == "optional" and r.status != "done":
                db.delete(r)
    db.commit()
    return get_task_settings(req.user_id, db)


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
    from ..models.sprint4 import ChallengeRecord
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
    from ..models.user import User
    u = db.query(User).filter_by(user_id=user_id).first()
    return (u.grade if u and u.grade else 6)


def _vocab_all_done(db: Session, user_id: str) -> tuple:
    """英语单词「全量完成」判定：今日新学全部完成 且 到期复习全部完成。

    返回 (done, new_done, review_done, learned_today, reviewed_today)。
    - 新学完成：新学额度用完（今日新学数达标或词库已无可学新词）
    - 复习完成：无剩余到期复习词（复习提交后 next_review_date 均推进到明天及以后）
    """
    from ..models.word import Word, WordBook
    from ..models.vocab import VocabProgress
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

    review_done = review_left == 0
    return (new_done and review_done), new_done, review_done, learned_today, reviewed_today


def _classical_all_done(db: Session, user_id: str) -> tuple:
    """古诗文「全量完成」判定：今日新背全部完成 且 到期复习全部完成。

    返回 (done, new_done, review_done, learned_today, reviewed_today)。
    """
    from ..models.classical import ClassicalText, ClassicalProgress
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

    review_done = review_left == 0
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


@router.post("/makeup/use", summary="使用补签卡补签某天")
def use_makeup_card(
    req: dict = Body(...),
    db: Session = Depends(get_db),
):
    """孩子直接补签过去某天为全勤（立即生效，扣 1 张补签卡）。

    参数（Body）：user_id、target_date（YYYY-MM-DD，必须早于今天）。
    返回：{balance, target_date, message}；余额不足/已补签过/日期非法或未来 返回 400。
    副作用：写 MakeupUsageLog（默认confirmed，计入连续天数/全勤）、扣 card.balance。
    无需家长密码（补签仅作用于过去日期）。
    """
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
    """查询补签卡余额。

    参数（Query）：user_id。
    返回：{user_id, balance}（无记录则 0）。
    副作用：无（只读）。无需家长密码。
    """
    return {"user_id": user_id, "balance": _get_makeup_balance(db, user_id)}


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


@router.get("/daily", summary="今日任务（3强制+3可选）")
def get_daily(user_id: str = Query(...), db: Session = Depends(get_db)):
    """返回今日任务面板（3 强制 + N 可选）。

    内部：确保今日任务行存在 → 按真实学习数据计算进度并自动完成非手动任务 →
         可选任务全完成发补签卡 → 强制全勤累计卡券 → 组装返回（含连续天数/补签卡余额）。
    参数（Query）：user_id。
    返回：{date, tasks[], mandatory_done/total, optional_done/total, streak_days, makeup_cards, ...}。
    副作用：可能更新 DailyTask 状态、发放补签卡、累计卡券进度。无需家长密码。
    """
    return _build_payload(db, user_id)


class ClaimRequest(BaseModel):
    user_id: str
    subject: str = None
    task_id: int = None


class ChildSubmitRequest(BaseModel):
    user_id: str
    task_id: int


@router.post("/daily/child_submit", summary="孩子提交完成申请（待家长确认）")
def child_submit_task(req: ChildSubmitRequest, db: Session = Depends(get_db)):
    """孩子点击完成按钮，状态变为 pending_confirm，等家长确认"""
    today = date.today()
    row = db.query(DailyTask).filter(
        DailyTask.id == req.task_id, DailyTask.user_id == req.user_id,
        DailyTask.task_date == today).first()
    if not row:
        raise HTTPException(404, "未找到该任务")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    if row.status == "pending_confirm":
        return _build_payload(db, req.user_id)
    row.status = "pending_confirm"
    row.progress = row.target
    db.commit()
    return _build_payload(db, req.user_id)


class MakeupCompleteRequest(BaseModel):
    user_id: str
    task_id: int


@router.post("/daily/makeup_complete", summary="孩子发起：用补签卡完成任意任务（待家长确认）")
def makeup_complete_task(req: MakeupCompleteRequest, db: Session = Depends(get_db)):
    """孩子发起用补签卡完成某任务：立即扣卡并生成 pending 记录，任务暂不完成。

    需家长在「家长面板」确认后生效；家长拒绝则退回补签卡、任务保持不变。
    """
    today = date.today()
    row = db.query(DailyTask).filter(
        DailyTask.id == req.task_id, DailyTask.user_id == req.user_id,
        DailyTask.task_date == today).first()
    if not row:
        raise HTTPException(404, "未找到该任务")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    # 同一任务已有待确认补签 → 不允许重复发起
    exist = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.user_id == req.user_id,
        MakeupUsageLog.task_id == req.task_id,
        MakeupUsageLog.status == "pending",
    ).first()
    if exist:
        raise HTTPException(400, "该任务已有待确认的补签申请")
    # 检查补签卡余额
    balance = _get_makeup_balance(db, req.user_id)
    if balance <= 0:
        raise HTTPException(400, "没有可用的补签卡")
    # 立即扣卡
    card = db.query(MakeupCard).filter(MakeupCard.user_id == req.user_id).first()
    card.balance -= 1
    card.total_used += 1
    # 生成待确认记录（任务暂不完成）
    log = MakeupUsageLog(
        user_id=req.user_id, target_date=today,
        task_id=req.task_id, status="pending",
    )
    db.add(log)
    db.commit()
    return _build_payload(db, req.user_id)


class MakeupConfirmRequest(BaseModel):
    user_id: str
    log_id: int
    action: str  # confirm / reject


@router.post("/makeup/confirm", summary="家长确认/拒绝补签卡使用")
def confirm_makeup(req: MakeupConfirmRequest, request: Request, db: Session = Depends(get_db)):
    """家长对「孩子发起的补签卡完成任务」进行最终确认或拒绝。

    - confirm：补签生效，关联任务标记为完成并发放金币；
    - reject ：补签卡退回（余额 +1、已用 -1），关联任务保持原状。
    需家长密码（由 http.js 自动附加 X-Parent-Pwd）。
    """
    ensure_parent_pwd(db, req.user_id, request)
    log = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.id == req.log_id, MakeupUsageLog.user_id == req.user_id).first()
    if not log:
        raise HTTPException(404, "未找到补签记录")
    if log.status != "pending":
        raise HTTPException(400, "该补签记录已处理")
    card = db.query(MakeupCard).filter(MakeupCard.user_id == req.user_id).first()

    if req.action == "confirm":
        log.status = "confirmed"
        if log.task_id:
            row = db.query(DailyTask).filter(DailyTask.id == log.task_id).first()
            if row and row.status != "done":
                row.progress = row.target
                row.status = "done"
                try:
                    from .pet import _grant_coins
                    _grant_coins(db, req.user_id, 5, "使用补签卡完成任务")
                except Exception:
                    pass
        db.commit()
        return {"status": "confirmed", "message": "补签已生效，任务完成 ✅"}
    elif req.action == "reject":
        log.status = "rejected"
        if card:
            card.balance += 1
            card.total_used = max(0, card.total_used - 1)
        db.commit()
        return {"status": "rejected", "message": "已拒绝，补签卡已退回 🔄"}
    else:
        raise HTTPException(400, "action 只能是 confirm 或 reject")


@router.get("/makeup/pending", summary="查询待家长确认的补签申请")
def list_pending_makeup(user_id: str = Query(...), db: Session = Depends(get_db)):
    """家长面板拉取孩子发起的、待确认的补签申请列表"""
    logs = db.query(MakeupUsageLog).filter(
        MakeupUsageLog.user_id == user_id,
        MakeupUsageLog.status == "pending",
    ).order_by(MakeupUsageLog.used_at.desc()).all()
    items = []
    for l in logs:
        title = ""
        if l.task_id:
            row = db.query(DailyTask).filter(DailyTask.id == l.task_id).first()
            title = row.title if row else ""
        items.append({
            "log_id": l.id,
            "task_id": l.task_id,
            "task_title": title,
            "target_date": str(l.target_date),
            "used_at": str(l.used_at),
        })
    return {"items": items}


@router.post("/daily/claim", summary="手动确认完成任务（需家长密码）")
def claim_task(req: ClaimRequest, request: Request, db: Session = Depends(get_db)):
    """家长手动确认完成一个手动任务（可选任务/家长自定义任务）。

    参数（Body）：user_id、task_id（优先）或 subject（兼容旧逻辑按学科确认强制任务）。
    请求头：必须携带 X-Parent-Pwd（ensure_parent_pwd，否则 403）——孩子不得自批。
    返回：刷新后的今日任务面板（_build_payload）。
    副作用：将对应 DailyTask 置 done 并发放金币 +5（仅手动类任务）；自动判定类任务拒绝手动确认。
    需要家长密码。
    """
    # 防刷：手动确认属于家长权限，孩子不得自批
    ensure_parent_pwd(db, req.user_id, request)
    today = date.today()
    row = None
    if req.task_id:
        # 按任务 id 精确确认（支持手动可选任务、家长自定义任务——同一学科可有多个）
        row = db.query(DailyTask).filter(
            DailyTask.id == req.task_id, DailyTask.user_id == req.user_id,
            DailyTask.task_date == today).first()
    else:
        if not req.subject:
            raise HTTPException(400, "需要提供 subject 或 task_id")
        # 兼容旧逻辑：按学科确认该科强制任务（每科默认唯一）
        rows = db.query(DailyTask).filter(
            DailyTask.user_id == req.user_id, DailyTask.task_date == today,
            DailyTask.subject == req.subject, DailyTask.task_type == "mandatory",
        ).all()
        row = rows[0] if rows else None
    if not row:
        raise HTTPException(404, "未找到该任务")
    if not row.manual:
        raise HTTPException(400, "该任务由学习数据自动判定，无需手动确认")
    if row.status == "done":
        return _build_payload(db, req.user_id)
    row.progress = row.target
    row.status = "done"
    # 心愿进度仅统计可选任务，强制任务手动确认不计入
    try:
        from .pet import _grant_coins
        _grant_coins(db, req.user_id, 5, "完成任务")
    except Exception:
        pass
    db.commit()
    return _build_payload(db, req.user_id)



# ═══════════════ 自定义任务子路由（拆分到 tasks_custom.py） ═══════════════
# 孩子端 /custom 与家长端 /custom-task 相关接口已拆入独立子路由，
# 路径仍为 /api/tasks/custom、/api/tasks/custom-task 等，对调用方零影响。
from . import tasks_custom
router.include_router(tasks_custom.router)
