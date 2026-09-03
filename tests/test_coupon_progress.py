# -*- coding: utf-8 -*-
"""兑换券进度累计回归测试（app/routers/rewards/exchange.sync_coupon_progress）

背景 bug（2026-08-19 线上反馈「卡券不会连续，每天进度都是 1/7」）：
- 旧实现每次全勤日都统计「今天往前 7 天」的缺卡，历史窗口积了 2 次缺卡后，
  即使孩子此后天天全勤也会被反复清零，进度永远卡在 1/7。
- 修复：缺卡清零后本轮从「清零当天」重新起算，只统计本轮起点之后的缺卡，
  旧缺卡不再拖累重新开始的连续。
"""
import datetime as _dt

from app.database import SessionLocal
from app.models.daily_task import DailyTask
from app.models.reward import RewardCoupon
import app.domains.engagement.routers.rewards.exchange as exchange_mod


class _FakeDate(_dt.date):
    _today = None

    @classmethod
    def today(cls):
        return cls._today


def _set_day(db, uid, day, full):
    """写入某天 3 科强制任务；full=True 全部 done，否则仅数学 pending（其余 done）。
    注意 SessionLocal 为 autoflush=False，写入后必须 flush 才能被后续查询看到。"""
    for subj, code, target in [("数学", "math_exam", 2),
                               ("英语", "eng_vocab", 20),
                               ("语文", "chi_classical", 5)]:
        done = full or subj != "数学"
        db.add(DailyTask(user_id=uid, task_date=day, subject=subj, task_code=code,
                         task_type="mandatory", title=code,
                         status="done" if done else "pending",
                         progress=target if done else 0, target=target))
    db.flush()


def _coupon(db, uid):
    c = RewardCoupon(user_id=uid, title="测试券", kind="custom",
                     required_days=7, required_within_days=0,
                     status="active", progress_days=0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_coupon_progress_continues_after_old_misses(client, monkeypatch):
    """历史有 2 次缺卡后连续全勤，进度应连续累计（不被旧缺卡反复清零）。

    场景：8-12 缺卡、8-13 全勤、8-14 全勤、8-15 缺卡、8-16 全勤
    → 8-16 全勤时本轮起点=8-14，本轮内只缺 8-15 一天 → 进度应为 3/7
    （旧实现看 7 天窗口含 8-12/8-15 两次缺卡 → 清零，永远 1/7）
    """
    uid = "卡券连续生"
    db = SessionLocal()
    try:
        c = _coupon(db, uid)
        base = _dt.date(2026, 8, 12)
        plan = {0: False, 1: True, 2: True, 3: False, 4: True}  # off: full
        for off, full in plan.items():
            _set_day(db, uid, base + _dt.timedelta(days=off), full)
        db.commit()
        try:
            for off in sorted(plan):
                _FakeDate._today = base + _dt.timedelta(days=off)
                monkeypatch.setattr(exchange_mod, "date", _FakeDate)
                exchange_mod.sync_coupon_progress(db, uid)
                db.expire_all()
        finally:
            monkeypatch.undo()
        db.refresh(c)
        assert c.progress_days == 3, (
            "清零后本轮应从本轮起点重新累计（期望 3/7），旧实现被旧缺卡反复清零卡在 1/7"
        )
        assert c.progress_date == "2026-08-16"
    finally:
        db.query(RewardCoupon).filter_by(user_id=uid).delete()
        db.query(DailyTask).filter_by(user_id=uid).delete()
        db.commit()
        db.close()


def test_coupon_progress_grants_at_required_days(client, monkeypatch):
    """连续 7 天全勤 → 进度 7/7 后自动获得 1 张，进度清零重计。"""
    uid = "卡券达标生"
    db = SessionLocal()
    try:
        c = _coupon(db, uid)
        base = _dt.date(2026, 8, 1)
        try:
            for off in range(7):
                _set_day(db, uid, base + _dt.timedelta(days=off), True)
                _FakeDate._today = base + _dt.timedelta(days=off)
                monkeypatch.setattr(exchange_mod, "date", _FakeDate)
                exchange_mod.sync_coupon_progress(db, uid)
                db.expire_all()
        finally:
            monkeypatch.undo()
        db.refresh(c)
        assert c.granted_count == 1, "连续 7 天全勤应获得 1 张"
        assert c.progress_days == 0, "达成后进度应清零，可继续累计下一张"
    finally:
        db.query(RewardCoupon).filter_by(user_id=uid).delete()
        db.query(DailyTask).filter_by(user_id=uid).delete()
        db.commit()
        db.close()
