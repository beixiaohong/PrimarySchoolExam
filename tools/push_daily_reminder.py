#!/usr/bin/env python3
"""每日学习提醒推送（OneSignal Web Push）

扫描「近 7 天活跃」的用户，按优先级各推一条：

  1. 今天有未完成的每日任务（daily_tasks.status='pending'）→ 提醒还剩几项
  2. 今天还没签到、但此前有连续签到 → 提醒别断签

用途与边界：
- 面向**学生端**，属自动事件（受每人每日推送上限与用户偏好开关约束，
  开关见 push_prefs.enable_study，过滤逻辑在 services/push.py 的 _load_audience）。
- 幂等：dedup_key = `study:{user_id}:{date}`，脚本重复执行（或调度器重触发）
  不会造成重复打扰。
- 🚫 铁律：本脚本只做「读 DB → 关会话 → 发 HTTP」，绝不在持有 DB 连接时调外部接口。

由 tools/scheduler.py 调度。**注意执行时刻不是凌晨 01:00**：推送必须在用户活跃时段
才有意义（凌晨推等于不推），所以此任务单独排在傍晚 19:00，见 JOBS 中的说明。

用法：
    python tools/push_daily_reminder.py --dry-run      # 只看会推给谁，不真发
    python tools/push_daily_reminder.py --limit 20     # 限量（调试）
    python tools/push_daily_reminder.py                # 正式执行
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.daily_task import DailyTask  # noqa: E402

# 活跃窗口：近 N 天有任务记录的用户才推送 —— 给长期不用的用户推送只会招致反感，
# 也浪费 OneSignal 配额
ACTIVE_DAYS = 7
# 单次最多处理人数（防止一次扫出全站用户把推送打爆；可按需上调）
DEFAULT_CAP = 2000
# 连续签到至少这么多天才值得提醒（新手还没形成习惯，提醒反成压力）
MIN_STREAK = 2


def _streak_of(dates, today):
    """由「已签到日期集合」算连续天数（含今天则从今天起；不含则从昨天起）

    注意必须用 date 对象比较：DailyTask.task_date 是 Column(Date)，
    读回是 datetime.date，与 str 比较恒为 False（历史踩过的坑）。
    """
    if not dates:
        return 0
    cur = today if today in dates else today - timedelta(days=1)
    n = 0
    while cur in dates:
        n += 1
        cur -= timedelta(days=1)
    return n


def collect_targets(cap=DEFAULT_CAP, today=None):
    """返回 [(user_id, title, body)]；只读，用完即关会话"""
    today = today or date.today()
    since = today - timedelta(days=ACTIVE_DAYS)

    db = SessionLocal()
    try:
        # 今天未完成的任务数（按用户聚合；必须用 func.count，
        # 不能用 dict(query(uid, id)) 冒充计数 —— 那样只剩「存在性」，条数是错的）
        pending = dict(
            db.query(DailyTask.user_id, func.count(DailyTask.id))
            .filter(DailyTask.task_date == today, DailyTask.status == "pending")
            .group_by(DailyTask.user_id).all())

        # 今天已签到的用户
        checked_today = {r[0] for r in db.query(DailyTask.user_id).filter(
            DailyTask.task_date == today, DailyTask.task_code == "checkin",
            DailyTask.status == "done").all()}

        # 近 7 天活跃用户
        active = {r[0] for r in db.query(DailyTask.user_id)
                  .filter(DailyTask.task_date >= since).distinct().all()}

        # 近 30 天签到日期（算连续天数用）
        rows = db.query(DailyTask.user_id, DailyTask.task_date).filter(
            DailyTask.task_date >= today - timedelta(days=30),
            DailyTask.task_code == "checkin", DailyTask.status == "done").all()
        checkins = {}
        for uid, d in rows:
            if not uid or d is None:
                continue
            # MySQL 可能回传 datetime，统一成 date（否则集合比较会落空）
            checkins.setdefault(uid, set()).add(d if isinstance(d, date) else d.date())
    finally:
        db.close()

    targets = []
    for uid in sorted(active):
        if len(targets) >= cap:
            break
        if not uid:
            continue
        # ① 今天有未完成任务：优先提醒（具体、可行动）
        left = pending.get(uid, 0)
        if left > 0:
            if left == 1:
                body = "今天还有 1 项任务没完成，去做完它吧～"
            else:
                body = "今天还有 %d 项任务没完成，别拖到明天哦～" % left
            targets.append((uid, "今天的学习任务还没完成", body))
            continue
        # ② 今天没签到但有连续记录：断签挽回（比笼统提醒更有效）
        if uid not in checked_today:
            streak = _streak_of(checkins.get(uid, set()), today)
            if streak >= MIN_STREAK:
                targets.append((uid, "已经连续打卡 %d 天" % streak,
                                "今天还没打卡，别让连续记录断掉～"))
    return targets


def main():
    ap = argparse.ArgumentParser(description="每日学习提醒推送")
    ap.add_argument("--dry-run", action="store_true", help="只统计不发送")
    ap.add_argument("--limit", type=int, default=DEFAULT_CAP, help="最多处理人数")
    args = ap.parse_args()

    today = date.today()
    targets = collect_targets(cap=args.limit, today=today)
    print("[push-reminder] %s 命中 %d 人（active<=%d 天）" % (today, len(targets), ACTIVE_DAYS))
    for uid, title, body in targets[:10]:
        print("   - %s | %s" % (uid, title))

    if args.dry_run:
        print("[push-reminder] dry-run：未实际发送")
        return
    if not targets:
        print("[push-reminder] 无需要提醒的用户")
        return

    # 会话已关闭，这里才发起外部 HTTP（铁律）
    from app.domains.platform.services import push

    if not push.push_configured():
        print("[push-reminder] 推送通道未配置（ONESIGNAL_APP_ID / REST_API_KEY 为空），本次跳过")
        return

    ok = 0
    for uid, title, body in targets:
        res = push.notify_user(uid, title, body, url="/#/home",
                               event=push.EVENT_STUDY,
                               data={"kind": "daily_reminder"},
                               dedup_key="study:%s:%s" % (uid, today))
        if res.get("ok"):
            ok += 1
    print("[push-reminder] 已提交 %d/%d 人（其余为已发过/偏好关闭/超每日上限）"
          % (ok, len(targets)))


if __name__ == "__main__":
    main()
