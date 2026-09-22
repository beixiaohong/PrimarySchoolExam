"""夜间静默时段（quiet hours）单元测试

背景：conftest 为让业务用例不受系统时间影响，在测试期把 `check_quiet_hours`
依赖覆写为空操作（否则 22:30–07:00 跑测试会大面积 403）。
为避免该特性因此失去覆盖，本文件以**直接调用函数**的方式验证其判定逻辑
（不经过 HTTP 栈，故不受依赖覆写影响），并用 monkeypatch 固定时间。
"""
from datetime import datetime

import pytest
from fastapi import HTTPException

import app.domains.platform.routers.quiet_hours as qh


class _Req:
    """最小 Request 替身：check_quiet_hours 只读取 request.url.path。"""

    def __init__(self, path):
        self.url = type("U", (), {"path": path})()


class _FakeDT:
    """固定 `datetime.now()` 的替身，使静默判定与真实系统时间无关。"""

    def __init__(self, hour, minute=0):
        self._t = datetime(2026, 1, 1, hour, minute)

    def now(self):
        return self._t


def _set_now(monkeypatch, hour, minute=0):
    monkeypatch.setattr(qh, "datetime", _FakeDT(hour, minute))


# ── 时段边界 ──
def test_in_quiet_start_boundary():
    assert qh._in_quiet(datetime(2026, 1, 1, 22, 30).time()) is True


def test_in_quiet_night_and_early_morning():
    assert qh._in_quiet(datetime(2026, 1, 1, 23, 59).time()) is True
    assert qh._in_quiet(datetime(2026, 1, 1, 0, 0).time()) is True
    assert qh._in_quiet(datetime(2026, 1, 1, 6, 59).time()) is True


def test_not_in_quiet_daytime():
    assert qh._in_quiet(datetime(2026, 1, 1, 7, 0).time()) is False
    assert qh._in_quiet(datetime(2026, 1, 1, 12, 0).time()) is False
    assert qh._in_quiet(datetime(2026, 1, 1, 22, 29).time()) is False


# ── 动作端点识别：动作拦截、只读放行 ──
def test_blocked_static_action_prefixes():
    assert qh._is_blocked_action("/api/exam/generate") is True
    assert qh._is_blocked_action("/api/vocab/learn") is True
    assert qh._is_blocked_action("/api/classical/quiz") is True


def test_readonly_paths_not_blocked():
    # 只读查看端点夜间仍需可用（学生可回顾历史）
    assert qh._is_blocked_action("/api/exam/list") is False
    assert qh._is_blocked_action("/api/study/progress") is False
    assert qh._is_blocked_action("/api/vocab/today") is False


def test_exam_dynamic_action_keywords():
    assert qh._is_blocked_action("/api/exam/12/mark-wrong") is True
    assert qh._is_blocked_action("/api/exam/12/submit-answers") is True
    assert qh._is_blocked_action("/api/exam/wrong/practice") is True
    assert qh._is_blocked_action("/api/exam/wrong/list") is False


# ── 依赖行为：夜间拦截 / 白天放行 ──
def test_check_quiet_hours_blocks_action_at_night(monkeypatch):
    _set_now(monkeypatch, 23, 0)
    with pytest.raises(HTTPException) as e:
        qh.check_quiet_hours(_Req("/api/exam/generate"))
    assert e.value.status_code == 403
    assert "夜间休息" in e.value.detail


def test_check_quiet_hours_allows_readonly_at_night(monkeypatch):
    _set_now(monkeypatch, 23, 0)
    assert qh.check_quiet_hours(_Req("/api/exam/list")) is None


def test_check_quiet_hours_allows_action_at_daytime(monkeypatch):
    _set_now(monkeypatch, 10, 0)
    assert qh.check_quiet_hours(_Req("/api/exam/generate")) is None
