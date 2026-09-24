"""每日签到功能测试（新功能 A）

钉死：① 幂等（同 user+date 重复 POST 不超发）；② 连续天数断签归零；③ 阶梯奖励触发
（第 3/7/15/30 天额外奖励）；④ status 字段（已签/月历/下一里程碑/余额）。

说明：conftest 不做事务回滚，故每用例用专属用户 + 显式 token，并在 finally 清理
该用户的 checkin 行，避免污染其他用例与钻石余额断言。

注意：MySQL 默认 REPEATABLE READ，长生命周期会话首次读后快照冻结，读不到其他会话
已提交的新余额。因此余额断言一律走 `_read_balance`（独立会话读最新已提交值），
并按「前后差值」判定，规避快照误读。
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.daily_task import DailyTask
from app.models.user import User
from app.domains.commerce.services.diamond import get_balance


CHECKIN_UID = "checkin_test_uid"


def _read_balance(uid: str) -> float:
    """用独立会话读取最新已提交余额，规避 REPEATABLE READ 快照误读。"""
    s = SessionLocal()
    try:
        return get_balance(s, uid)
    finally:
        s.close()


def _token_for(db: Session, uid: str) -> str:
    """为专属测试用户签发/复用登录 token（使 require_self 通过）"""
    import secrets
    from datetime import datetime, timedelta as _td
    u = db.query(User).filter(User.user_id == uid).first()
    if not u:
        u = User(user_id=uid, nickname=uid, grade=6, subject="英语")
        db.add(u)
    u.token = secrets.token_urlsafe(32)
    u.token_expires_at = datetime.now() + _td(hours=24)
    db.commit()
    return u.token


def _cleanup(db: Session, uid: str):
    db.query(DailyTask).filter(
        DailyTask.user_id == uid, DailyTask.task_code == "checkin").delete()
    db.commit()


def _seed_checkins(db: Session, uid: str, days_back: int, gap_yesterday: bool = False):
    """为 uid 插入过去 days_back 天的连续签到（不含今天），可制造断签。

    gap_yesterday=True 时跳过「昨天」，使 streak 从今天起只能数到 0（断签）。
    """
    today = date.today()
    for k in range(1, days_back + 1):
        d = today - timedelta(days=k)
        if gap_yesterday and d == today - timedelta(days=1):
            continue
        db.add(DailyTask(
            user_id=uid, task_date=d, subject="其他", task_code="checkin",
            title="每日签到", target=1, progress=1, status="done",
            manual=False, task_type="optional",
        ))
    db.commit()


def test_checkin_idempotent_no_over_issue(client):
    """重复 POST 同一天：第二次 already_signed=True、reward=0，不重复发钻"""
    db = SessionLocal()
    try:
        _cleanup(db, CHECKIN_UID)
        tok = _token_for(db, CHECKIN_UID)
        h = {"Authorization": f"Bearer {tok}"}
        bal0 = _read_balance(CHECKIN_UID)

        r1 = client.post("/api/checkin", headers=h)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1["signed_today"] is True
        assert j1["already_signed"] is False
        assert j1["reward"] == 2.0, f"基础奖励应为 2，实际 {j1['reward']}"
        assert j1["bonus"] == 0.0
        bal1 = _read_balance(CHECKIN_UID)
        assert abs((bal1 - bal0) - 2.0) < 1e-6, f"钻石应 +2，实际 +{bal1 - bal0}"

        r2 = client.post("/api/checkin", headers=h)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()
        assert j2["already_signed"] is True
        assert j2["reward"] == 0.0, "重复签到不应再发钻（幂等防超发）"
        bal2 = _read_balance(CHECKIN_UID)
        assert abs(bal2 - bal1) < 1e-6, "第二次签到钻石余额不应变化"
    finally:
        _cleanup(db, CHECKIN_UID)
        db.close()


def test_checkin_streak_and_ladder(client):
    """连续 N 天后签到：streak=N+1，命中第 3 天阶梯额外 +5"""
    db = SessionLocal()
    try:
        _cleanup(db, CHECKIN_UID)
        # 过去 2 天连续签到 → 今天签到第 3 天，触发阶梯 bonus=5
        _seed_checkins(db, CHECKIN_UID, days_back=2)
        tok = _token_for(db, CHECKIN_UID)
        h = {"Authorization": f"Bearer {tok}"}
        bal0 = _read_balance(CHECKIN_UID)

        r = client.post("/api/checkin", headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["streak"] == 3, f"连续天数应为 3，实际 {j['streak']}"
        assert j["bonus"] == 5.0, f"第 3 天阶梯奖励应为 5，实际 {j['bonus']}"
        assert j["reward"] == 7.0, f"本次应得 2+5=7，实际 {j['reward']}"
        # 用独立会话读最新已提交余额，按差值判定，规避 REPEATABLE READ 快照
        assert abs((_read_balance(CHECKIN_UID) - bal0) - 7.0) < 1e-6
    finally:
        _cleanup(db, CHECKIN_UID)
        db.close()


def test_checkin_streak_reset_on_gap(client):
    """断签（昨天缺失）后签到：streak=1（仅今天），无阶梯奖励"""
    db = SessionLocal()
    try:
        _cleanup(db, CHECKIN_UID)
        # 制造断签：跳过昨天，仅更早的 5 天连续
        today = date.today()
        for k in range(2, 7):  # 2..6 天前连续，昨天(k=1)缺失
            db.add(DailyTask(
                user_id=CHECKIN_UID, task_date=today - timedelta(days=k),
                subject="其他", task_code="checkin", title="每日签到",
                target=1, progress=1, status="done", manual=False,
                task_type="optional"))
        db.commit()
        tok = _token_for(db, CHECKIN_UID)
        h = {"Authorization": f"Bearer {tok}"}

        r = client.post("/api/checkin", headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        # 昨天缺失 → 连续天数只能从今天起算 = 1
        assert j["streak"] == 1, f"断签后 streak 应为 1，实际 {j['streak']}"
        assert j["bonus"] == 0.0
        assert j["reward"] == 2.0
    finally:
        _cleanup(db, CHECKIN_UID)
        db.close()


def test_checkin_status_fields(client):
    """GET /status：已签状态、月历含今天、下一里程碑、余额"""
    db = SessionLocal()
    try:
        _cleanup(db, CHECKIN_UID)
        # 先签到第 2 天（无阶梯），使 streak=2
        _seed_checkins(db, CHECKIN_UID, days_back=1)
        tok = _token_for(db, CHECKIN_UID)
        h = {"Authorization": f"Bearer {tok}"}
        client.post("/api/checkin", headers=h)  # streak -> 2

        r = client.get("/api/checkin/status", headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["signed_today"] is True
        assert j["streak"] == 2
        # 下一里程碑应为第 3 天
        assert j["next_reward_day"] == 3, f"下一里程碑应为 3，实际 {j['next_reward_day']}"
        # 月历最后一天（今天）应 signed=True
        cal = j["month_calendar"]
        assert cal[-1]["signed"] is True
        assert cal[-1]["day"] == date.today().day
        # 阶梯表完整
        ladder_days = {x["day"] for x in j["ladder"]}
        assert ladder_days == {3, 7, 15, 30}
        assert j["diamonds"] >= 0
    finally:
        _cleanup(db, CHECKIN_UID)
        db.close()
