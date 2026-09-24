"""每日签到 + 连续奖励（新功能 A，2026Q4）

设计要点（复用既有能力，零新表）：
- 复用 `daily_tasks` 表：每日签到落一行 `task_code="checkin"`、`subject="其他"`、
  `task_type="optional"`、`status="done"`；唯一键 (user_id, task_date, task_code)
  保证每日至多一行，天然支撑幂等。
- 连续天数**独立**计算（基于 checkin 行集合），不与「全勤 streak」（badges/assistant 口径）
  耦合，避免被「仅打开 App 未学习」污染。
- 奖励经 `commerce.contracts.DiamondService.grant`（底层 grant 自带 WITH FOR UPDATE 行锁，
  并发安全）发放；基础奖励 + 里程碑阶梯。**跨域必须走 commerce.contracts**，不直连
  commerce.services.diamond（由 .importlinter 域独立契约强制）。
- 签到同时是一次行为事件（新功能 C）：经 `events.award(..., EVENT_CHECKIN)` 加经验。

铁律合规：纯 DB 操作，无外部/AI 调用，不持连接等阻塞调用；grant 内部自带短会话提交。
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.commerce.contracts import DiamondService
from app.domains.engagement.services.events import EVENT_CHECKIN, award
from app.domains.identity.contracts import require_self
from app.models.daily_task import DailyTask
from app.models.user import User

router = APIRouter(tags=["checkin"])

CHECKIN_CODE = "checkin"
# 基础奖励：每次签到固定获得钻石
CHECKIN_BASE_REWARD = 2.0
# 阶梯奖励：连续签到达到 key 天，额外奖励 value 钻石（仅在该天触发一次）
CHECKIN_LADDER = {3: 5.0, 7: 10.0, 15: 20.0, 30: 50.0}


def _ensure_checkin_row(db: Session, uid: str, today: date) -> bool:
    """确保今日签到行存在并置 done，返回是否「本次新签」。

    幂等：今日已签（status=done）返回 False，不重复发钻；否则 upsert 并置 done。
    """
    row = db.query(DailyTask).filter(
        DailyTask.user_id == uid, DailyTask.task_date == today,
        DailyTask.task_code == CHECKIN_CODE,
    ).first()
    if row and row.status == "done":
        return False  # 今日已签
    if not row:
        row = DailyTask(
            user_id=uid, task_date=today, subject="其他",
            task_code=CHECKIN_CODE, title="每日签到",
            target=1, progress=1, status="done", manual=False,
            task_type="optional",
        )
        db.add(row)
    else:
        row.status = "done"
        row.progress = 1
    db.commit()
    return True


def _checkin_dates(db: Session, uid: str) -> set:
    """返回该用户所有已签到日期集合（date 对象）"""
    rows = db.query(DailyTask.task_date).filter(
        DailyTask.user_id == uid, DailyTask.task_code == CHECKIN_CODE,
        DailyTask.status == "done",
    ).all()
    return {r[0] for r in rows}


def _checkin_streak(db: Session, uid: str) -> int:
    """连续签到天数：从今天（若已签）或昨天起向前连续计数。"""
    dates = _checkin_dates(db, uid)
    today = date.today()
    d = today if today in dates else today - timedelta(days=1)
    streak = 0
    while d in dates:
        streak += 1
        d -= timedelta(days=1)
        if streak > 3660:  # 防御性上限
            break
    return streak


def _month_calendar(db: Session, uid: str, today: date) -> list:
    """本月签到日历：[{day, signed}]（仅到今天，不含未来）"""
    dates = _checkin_dates(db, uid)
    d = today.replace(day=1)
    cal = []
    while d <= today:
        cal.append({"day": d.day, "signed": d in dates})
        d += timedelta(days=1)
    return cal


def _next_reward_day(streak: int):
    """下一个阶梯里程碑天数（大于当前 streak 的最小 key），无则 None"""
    for day in sorted(CHECKIN_LADDER):
        if day > streak:
            return day
    return None


@router.post("")
def do_checkin(current_user: User = Depends(require_self),
               db: Session = Depends(get_db)) -> dict:
    """每日签到（幂等）。

    返回：signed_today / already_signed / streak / reward（本次获得钻石，含基础+阶梯）
    / bonus（阶梯额外部分）/ next_reward_day / diamonds（签到后余额）。
    """
    uid = current_user.user_id
    today = date.today()
    is_new = _ensure_checkin_row(db, uid, today)
    streak = _checkin_streak(db, uid)

    reward = 0.0
    bonus = 0.0
    if is_new:  # 仅新签才发放，重复 POST 不发（幂等防超发）
        reward = CHECKIN_BASE_REWARD
        bonus = CHECKIN_LADDER.get(streak, 0.0)
        if bonus:
            reward += bonus
        if reward > 0:
            DiamondService.grant(db, uid, reward, biz="daily_checkin")
        # 签到本身也是一次行为事件（新功能 C）：加经验，并评估徽章解锁。
        # 只在 is_new 分支内调用，重复 POST 不会重复加经验（与发钻同口径幂等）。
        award(db, uid, EVENT_CHECKIN)

    return {
        "signed_today": True,
        "already_signed": not is_new,
        "streak": streak,
        "reward": reward,
        "bonus": bonus,
        "next_reward_day": _next_reward_day(streak),
        "diamonds": DiamondService.balance(db, uid),
    }


@router.get("/status")
def checkin_status(current_user: User = Depends(require_self),
                  db: Session = Depends(get_db)) -> dict:
    """签到状态：今日是否已签 / 连续天数 / 本月日历 / 下一里程碑 / 阶梯表 / 余额。"""
    uid = current_user.user_id
    today = date.today()
    dates = _checkin_dates(db, uid)
    streak = _checkin_streak(db, uid)
    return {
        "signed_today": today in dates,
        "streak": streak,
        "month_calendar": _month_calendar(db, uid, today),
        "next_reward_day": _next_reward_day(streak),
        "ladder": [{"day": d, "bonus": b} for d, b in sorted(CHECKIN_LADDER.items())],
        "base_reward": CHECKIN_BASE_REWARD,
        "diamonds": DiamondService.balance(db, uid),
    }
