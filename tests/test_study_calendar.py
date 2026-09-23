"""学习日历测试：聚合每日任务 / 专注 / 心情打卡

验证 GET /api/calendar：
- 当日有任务完成/专注/心情打卡时 checked_in=True 且对应计数正确
- 连续打卡天数 streak ≥ 1
- 仅按 user_id 隔离（其它用户无数据）
"""
from datetime import date, datetime

import pytest

from app.database import SessionLocal
from app.models.daily_task import DailyTask
from app.models.focus import FocusSession
from app.models.mood import MoodCheckin


def test_calendar_aggregates_today(client):
    """构造今日任务+专注+心情，日历正确聚合且 streak≥1"""
    uid = "cal_user"
    db = SessionLocal()
    today = date.today()
    try:
        db.add(DailyTask(user_id=uid, task_date=today, subject="数学",
                         task_code="t1", title="完成任务", target=1,
                         progress=1, status="done"))
        db.add(FocusSession(user_id=uid, minutes=40, created_at=datetime.now()))
        db.add(MoodCheckin(user_id=uid, check_date=today, mood="happy", note="不错"))
        db.commit()

        r = client.get(f"/api/calendar?user_id={uid}&days=30")
        assert r.status_code == 200, r.text
        body = r.json()
        ds = today.isoformat()
        today_cell = [d for d in body["days"] if d["date"] == ds]
        assert today_cell, "今日应出现在日历中"
        cell = today_cell[0]
        assert cell["tasks_done"] >= 1
        assert cell["focus_minutes"] >= 40
        assert cell["mood"] == "happy"
        assert cell["checked_in"] is True
        assert body["streak"] >= 1
        assert body["total_days"] >= 1
        assert body["total_focus_minutes"] >= 40
    finally:
        db.close()


def test_calendar_isolated_by_user(client):
    """其它用户（无数据）日历今日无打卡、streak=0"""
    uid = "cal_other_empty"
    r = client.get(f"/api/calendar?user_id={uid}&days=30")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["streak"] == 0
    assert body["total_days"] == 0
    ds = date.today().isoformat()
    cell = [d for d in body["days"] if d["date"] == ds]
    if cell:
        assert cell[0]["checked_in"] is False
