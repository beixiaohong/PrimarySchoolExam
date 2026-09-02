"""每日任务 · 服务层（设置读写、任务行生成、payload 构建、全勤与补签卡）

从原 common.py 拆分而来：负责家长设置的读写、当日任务行的生成与刷新、
/ 每日任务 payload 的组装、全勤/连续天数统计，以及补签卡的发放与余额查询。
只含业务逻辑，不含路由端点。
"""
import json
import logging
from datetime import date, timedelta

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.daily_task import DailyTask
from app.models.makeup_card import MakeupCard, MakeupUsageLog
from app.models.parent_custom_task import ParentCustomTask

from .constants import (
    SUBJECTS, MANDATORY_TASKS, OPTIONAL_POOL,
    _UNCONFIGURABLE_CODES, CONFIGURABLE_CODES, MIN_TARGET, MAX_TARGET,
    QUOTA_KEYS, STUDY_FLAG_KEYS, _normalize_mandatory,
    _get_mandatory_codes, _task_def_by_code, _setting_target,
    _is_task_enabled, _pick_daily_optional, _display_title,
)
from .progress import _task_progress, _daily_task_feasible

logger = logging.getLogger(__name__)


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


def get_daily_quota(db: Session, user_id: str, key: str) -> int:
    """读家长配置的每日额度（quotas），未配置时返回默认值"""
    lo, hi, default = QUOTA_KEYS[key]
    settings = _load_settings(db, user_id)
    try:
        v = int(settings.get("quotas", {}).get(key, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


# ═══════════════ 任务行生成 ═══════════════

def _ensure_today_rows(db: Session, user_id: str) -> list:
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
    # 惰性执行心愿「有效期+清零重发」规则（孩子打开面板即触发，无需定时任务）
    try:
        from app.routers.rewards.common import _expire_wishes
        _expire_wishes(db, user_id)
    except Exception:
        pass
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
            # 内容可行性兜底：若题库内容不足铁定达不到 target（如数学练习 target=2 但仅 1 套卷），
            # 自动判完成，避免「永远无法完成」阻塞全勤（系统/内容原因，非孩子不努力）。
            if not _daily_task_feasible(db, user_id, row.task_code, row.subject, row.target):
                row.progress = row.target
                row.status = "done"
                # 可选任务自动完成仍计入心愿进度
                if (getattr(row, 'task_type', 'mandatory') or 'mandatory') == "optional":
                    try:
                        from app.routers.rewards import inc_active_wish_progress
                        inc_active_wish_progress(db, user_id, 1)
                    except Exception:
                        pass
                continue
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
