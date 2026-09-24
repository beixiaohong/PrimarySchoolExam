"""成就系统升级（新功能 B，2026Q4）测试

钉死：
① 事件驱动**只评估相关徽章**（用 exam_done 触发时，即使 mood 阈值已达成也不得授予 mood_7）；
② 实时授予（阈值达成即授予，不等下次访问徽章墙）；
③ 授予**幂等**（重复触发不重复插入，badge_earned 仅一行）；
④ 进度 current/target/pct 计算（达标 100、未达标按比例）；
⑤ 未登记事件不授予任何徽章（避免静默退化为全量扫描）；
⑥ 埋点端到端：心情打卡集齐 7 天时，mood_7 在**该次请求内**即时落库；
⑦ 内部 bug 回归：`DailyTask.task_date` 是 Date 列，全勤连续天数必须按 date 对象比较
   （原实现 `str(d) in dates` 恒为 False → streak 恒 0、streak_7/30 永不可得）。

说明：conftest 不做事务回滚 → 每用例用专属用户 + 显式 token，finally 清理自身数据
（含 badge_earned / mood_checkins / daily_tasks）。跨会话读已提交值用独立 SessionLocal()，
规避 MySQL REPEATABLE READ 快照冻结。
"""
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.domains.engagement.services.achievement import (
    EVENT_EXAM_DONE,
    EVENT_MOOD_DONE,
    EVENT_TASK_DONE,
    list_badges,
    try_grant,
)
from app.models.badge import BadgeEarned
from app.models.daily_task import DailyTask
from app.models.mood import MoodCheckin
from app.models.user import User

ACH_UID = "ach_test_uid"


def _token_for(db: Session, uid: str) -> str:
    """为专属测试用户签发/复用登录 token（使 require_self 通过）"""
    u = db.query(User).filter(User.user_id == uid).first()
    if not u:
        u = User(user_id=uid, nickname=uid, grade=6, subject="英语")
        db.add(u)
    u.token = secrets.token_urlsafe(32)
    u.token_expires_at = datetime.now() + timedelta(hours=24)
    db.commit()
    return u.token


def _cleanup(db: Session, uid: str):
    """清空该测试用户的成就与行为数据，保证重复运行互不污染"""
    db.query(BadgeEarned).filter(BadgeEarned.user_id == uid).delete()
    db.query(MoodCheckin).filter(MoodCheckin.user_id == uid).delete()
    db.query(DailyTask).filter(DailyTask.user_id == uid).delete()
    db.commit()


def _earned_codes(db: Session, uid: str) -> set:
    return {b.badge_code for b in db.query(BadgeEarned).filter(
        BadgeEarned.user_id == uid).all()}


def _earned_codes_fresh(uid: str) -> set:
    """用独立会话读最新已提交值（规避 REPEATABLE READ 快照冻结）"""
    s = SessionLocal()
    try:
        return _earned_codes(s, uid)
    finally:
        s.close()


def _seed_moods(db: Session, uid: str, n: int, end_offset: int = 0):
    """插入 n 条心情打卡（自 today-end_offset 逐日往前），用于构造 moods 指标"""
    base = date.today() - timedelta(days=end_offset)
    for i in range(n):
        db.add(MoodCheckin(user_id=uid, check_date=base - timedelta(days=i),
                           mood="great", note=""))
    db.commit()


# ══════════════════════════ 服务层：事件驱动语义 ══════════════════════════

def test_event_scoped_grant_and_idempotent():
    """事件只评估相关徽章；达标即时授予；重复触发幂等；未登记事件不授予"""
    db = SessionLocal()
    try:
        _cleanup(db, ACH_UID)
        _seed_moods(db, ACH_UID, 7)          # mood 已 7 天 → mood_7 阈值达成

        # ① 用 exam_done 评估：不得授予 mood_7（证明只评估该事件的徽章，而非全量扫描）
        assert try_grant(db, ACH_UID, EVENT_EXAM_DONE) == []
        assert "mood_7" not in _earned_codes(db, ACH_UID)

        # ② 用 mood_done 评估：阈值达成 → 即时授予
        assert try_grant(db, ACH_UID, EVENT_MOOD_DONE) == ["mood_7"]
        assert "mood_7" in _earned_codes(db, ACH_UID)

        # ③ 幂等：再次触发不重复授予，表内仍仅 1 行
        assert try_grant(db, ACH_UID, EVENT_MOOD_DONE) == []
        n = db.query(BadgeEarned).filter(
            BadgeEarned.user_id == ACH_UID,
            BadgeEarned.badge_code == "mood_7").count()
        assert n == 1, f"幂等失败：badge_earned 出现 {n} 行"

        # ⑤ 未登记事件：不授予任何徽章（即使阈值已达成）
        assert try_grant(db, ACH_UID, "no_such_event") == []
        assert _earned_codes(db, ACH_UID) == {"mood_7"}
    finally:
        _cleanup(db, ACH_UID)
        db.close()


def test_progress_and_categories():
    """徽章墙进度：达标 pct=100、未达标按比例；分类齐全且计数自洽"""
    db = SessionLocal()
    try:
        _cleanup(db, ACH_UID)
        _seed_moods(db, ACH_UID, 7)

        r = list_badges(db, ACH_UID)
        assert r["total"] == 18, f"徽章总数应为 18，实际 {r['total']}"

        by_code = {i["code"]: i for i in r["items"]}

        # ④ 已达标：mood_7 current=7/target=7/pct=100 且已得
        m7 = by_code["mood_7"]
        assert m7["earned"] is True
        assert m7["progress"] == {"current": 7, "target": 7, "pct": 100}
        assert m7["earned_at"], "已得徽章应带获得日期"

        # ④ 未达标：streak_7 无每日任务记录 → current=0、pct=0、未得
        s7 = by_code["streak_7"]
        assert s7["earned"] is False
        assert s7["progress"] == {"current": 0, "target": 7, "pct": 0}
        assert s7["earned_at"] is None

        # 分类：三项且 total 求和等于徽章总数
        assert len(r["categories"]) == 3
        assert {c["key"] for c in r["categories"]} == {"study", "persist", "social"}
        assert sum(c["total"] for c in r["categories"]) == r["total"]
        assert all(i["category"] in ("study", "persist", "social") for i in r["items"])
    finally:
        _cleanup(db, ACH_UID)
        db.close()


def test_streak_metric_counts_consecutive_done_days():
    """⑦ 回归：全勤连续天数按 date 对象比较（原 str(d) in dates 恒 0 → streak 徽章永不可得）"""
    db = SessionLocal()
    try:
        _cleanup(db, ACH_UID)
        today = date.today()
        for i in range(7):      # 连续 7 天（含今天）有 done 任务
            db.add(DailyTask(
                user_id=ACH_UID, task_date=today - timedelta(days=i),
                subject="数学", task_code="math_practice", title="数学练习",
                target=1, progress=1, status="done", manual=False, task_type="mandatory"))
        db.commit()

        assert try_grant(db, ACH_UID, EVENT_TASK_DONE) == ["streak_7"]
        assert "streak_30" not in _earned_codes(db, ACH_UID)
    finally:
        _cleanup(db, ACH_UID)
        db.close()


# ══════════════════════════ HTTP 层：契约与埋点 ══════════════════════════

def test_badges_api_contract(client):
    """/api/badges 需鉴权，返回 progress/category/earned/earned_at 字段"""
    db = SessionLocal()
    try:
        _cleanup(db, ACH_UID)
        tok = _token_for(db, ACH_UID)
        h = {"Authorization": f"Bearer {tok}"}

        # 注：conftest 的 AuthClient 会为请求中出现的 user_id 自动补签 token，
        # 故无法用本 client 构造「未鉴权」场景；/api/badges 的鉴权由 main.py 的
        # user_auth_deps（Depends(require_self)）统一承载，401 场景由其余鉴权用例覆盖。
        r = client.get(f"/api/badges?user_id={ACH_UID}", headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["total"] == 18
        assert len(j["categories"]) == 3

        item = next(i for i in j["items"] if i["code"] == "mood_7")
        assert set(item["progress"].keys()) == {"current", "target", "pct"}
        assert item["progress"]["target"] == 7
        assert item["category"] == "persist"
        assert item["earned"] is False
        assert item["earned_at"] is None
    finally:
        _cleanup(db, ACH_UID)
        db.close()


def test_mood_checkin_triggers_realtime_badge(client):
    """⑥ 埋点端到端：心情打卡集齐第 7 天时，mood_7 在该请求内即时落库（无需再访问徽章墙）"""
    db = SessionLocal()
    try:
        _cleanup(db, ACH_UID)
        tok = _token_for(db, ACH_UID)
        _seed_moods(db, ACH_UID, 6, end_offset=1)   # 前 6 天：today-6 .. today-1
        assert _earned_codes(db, ACH_UID) == set()

        r = client.post("/api/mood/checkin",
                        headers={"Authorization": f"Bearer {tok}"},
                        json={"user_id": ACH_UID, "mood": "great", "note": ""})
        assert r.status_code == 200, r.text

        # 实时性验证：打卡请求返回时徽章已在库中（本用例从未调用 /api/badges）
        assert "mood_7" in _earned_codes_fresh(ACH_UID), "打卡埋点未实时授予 mood_7"
    finally:
        _cleanup(db, ACH_UID)
        db.close()
