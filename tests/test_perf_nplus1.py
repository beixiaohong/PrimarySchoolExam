# -*- coding: utf-8 -*-
"""P1 性能：DailyTask N+1 循环查回归测试

治理总纲点名的三处「逐日/逐周拆 N 次 DB 往返」已改为按区间一次性批量取，
内存聚合。本文件用 SQLAlchemy 事件监听器**实测 daily_task 查询次数**，
证明优化真实生效（streak 60→1、full_days 7→1），并校验语义等价。
"""
import datetime as _dt

import pytest
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models.daily_task import DailyTask

import app.domains.platform.routers.assistant as assistant_mod
import app.domains.platform.routers.ai as ai_mod
import app.domains.engagement.contracts as contracts_mod


def _count_daily_task_queries(fn, *args, **kwargs):
    """在 fn 执行期间统计命中 daily_task 的 SQL 条数，证明无逐日循环查。"""
    counter = {"n": 0}

    def _listen(conn, cursor, statement, parameters, context, executemany):
        if "daily_task" in statement.lower():
            counter["n"] += 1

    event.listen(engine, "after_cursor_execute", _listen)
    try:
        result = fn(*args, **kwargs)
    finally:
        event.remove(engine, "after_cursor_execute", _listen)
    return result, counter["n"]


def _add_day(db, uid, day, done_count=1, status="done"):
    """写入某天 done_count 条强制任务，status 控制是否 done。flush 后可见。"""
    for i in range(done_count):
        db.add(DailyTask(user_id=uid, task_date=day, subject="数学",
                         task_code=f"math_{i}", task_type="mandatory",
                         title=f"t{i}", status=status,
                         progress=1 if status == "done" else 0, target=1))
    db.flush()


def _stub_growth_pet(monkeypatch):
    """打桩成长树/宠物余额服务（其实现也会查 daily_task），隔离 streak 查询计数。"""
    monkeypatch.setattr(contracts_mod.PetService, "balance", lambda db, uid: 0)
    monkeypatch.setattr(contracts_mod.GrowthTreeService, "score", lambda db, uid: 0)


# ───────────────────────── assistant 连续打卡 ─────────────────────────

def test_assistant_streak_no_per_day_query(client, monkeypatch):
    """连续 3 天全勤 → 画像应含『已连续 3 天完成任务』；daily_task 查询仅 2 次
    （今日任务 1 + streak 批量 1），而非旧的 1 + 最多 60 逐日查。"""
    _stub_growth_pet(monkeypatch)
    uid = "连续打卡生"
    db = SessionLocal()
    try:
        today = _dt.date.today()
        for off in (0, 1, 2):  # 今天/昨天/前天 全 done
            _add_day(db, uid, today - _dt.timedelta(days=off), done_count=2)
        db.commit()

        profile, n = _count_daily_task_queries(
            assistant_mod._build_profile, db, uid, 6, "数学")

        assert "已连续 3 天完成任务" in profile, f"连续打卡文案缺失：{profile}"
        # 旧实现 streak 逐日查最坏 60 次；新实现固定 1 次（加今日任务 1 次 = 2）。
        assert n <= 3, f"连续打卡不应逐日查（期望 ≤3 次 daily_task 查询，实际 {n} 次）"
    finally:
        db.query(DailyTask).filter_by(user_id=uid).delete()
        db.commit()
        db.close()


def test_assistant_streak_breaks_on_gap(client, monkeypatch):
    """今天 done、昨天缺卡 → 连续天数应为 1（中断即停）。"""
    _stub_growth_pet(monkeypatch)
    uid = "打卡中断生"
    db = SessionLocal()
    try:
        today = _dt.date.today()
        _add_day(db, uid, today, done_count=2)                        # 今天 done
        _add_day(db, uid, today - _dt.timedelta(days=2), done_count=2)  # 前天 done，昨天缺
        db.commit()

        profile, _ = _count_daily_task_queries(
            assistant_mod._build_profile, db, uid, 6, "数学")
        assert "已连续 1 天完成任务" in profile, f"中断后应为 1 天：{profile}"
    finally:
        db.query(DailyTask).filter_by(user_id=uid).delete()
        db.commit()
        db.close()


# ───────────────────────── ai 周报全勤天数 ─────────────────────────

def test_ai_weekly_full_days_no_per_day_query(client):
    """上周 3 天满勤（≥3 done）→ full_days==3，且 daily_task 查询仅 1 次（非 7）。

    _aggregate_week 统计的是『上周』（_week_range 返回上周一~上周日）。直接在返回的
    周区间内写 3 天各 3 条 done；旧实现 range(7) 逐日 count 共 7 次 DB 往返。
    """
    uid = "全勤周报生"
    db = SessionLocal()
    try:
        ws, we = ai_mod._week_range()  # 上周一 ~ 上周日
        for off in (0, 1, 2):  # 上周前三日（均 ≤ 今天，合法）
            _add_day(db, uid, ws + _dt.timedelta(days=off), done_count=3)
        db.commit()

        stats, n = _count_daily_task_queries(ai_mod._aggregate_week, db, uid)
        assert stats["full_days"] == 3, f"全勤天数应为 3，实际 {stats['full_days']}"
        assert n == 1, f"全勤统计不应逐日 count（期望 1 次 daily_task 查询，实际 {n} 次）"
    finally:
        db.query(DailyTask).filter_by(user_id=uid).delete()
        db.commit()
        db.close()
