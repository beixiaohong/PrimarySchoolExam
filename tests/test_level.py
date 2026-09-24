"""等级 / 成长体系测试（新功能 C）

钉死六件事：
① 经验增量累加（`add_exp` 落库、读时零聚合）；
② 阈值边界：经验**恰好等于** min_exp 即升级（`>=` 语义），差 1 点不升；
③ 一次加大量经验可跨多级，中间等级奖励**合并发放不漏**；
④ 并发 `add_exp` 不丢更新（`WITH FOR UPDATE` 行锁）；
⑤ `GET /api/level` 字段契约（等级/进度/下一级/阶梯完整、满级语义）；
⑥ 事件与经验规则一致性：未登记事件不加经验、登记事件按规则加经验。

说明：conftest 不做事务回滚，故用专属用户 + 显式 token，每用例 finally 重置该用户的
level/exp，避免跨用例污染。

MySQL 默认 REPEATABLE READ：长生命周期会话首次读后快照冻结，读不到其他会话已提交的新值。
因此所有跨会话断言（exp / 余额）都走**独立会话**读取最新已提交值。
"""
import sys
import threading
from pathlib import Path

from sqlalchemy.orm import Session

# tools/ 不是包，直接把项目根加入路径以便导入回填工具（验证其口径与列名）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from tools.backfill_level_exp import compute_exp  # noqa: E402
from app.models.level import LevelConfig
from app.models.user import User
from app.domains.commerce.services.diamond import get_balance
from app.domains.engagement.contracts import AwardService, LevelService
from app.domains.engagement.services.events import (
    EVENT_EXAM_DONE,
    EVENT_TASK_DONE,
    award,
)
from app.domains.engagement.services.level import (
    LEVEL_FALLBACK,
    ensure_level_config,
    level_for_exp,
)


LEVEL_UID = "level_test_uid"


def _read_exp(uid: str) -> int:
    """独立会话读取最新已提交经验（规避 REPEATABLE READ 快照误读）"""
    s = SessionLocal()
    try:
        u = s.query(User).filter(User.user_id == uid).first()
        return int(u.exp or 0) if u else 0
    finally:
        s.close()


def _read_balance(uid: str) -> float:
    """独立会话读取最新已提交钻石余额"""
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


def _reset(db: Session, uid: str):
    """把专属用户经验/等级归零（保持 token 不动）"""
    u = db.query(User).filter(User.user_id == uid).first()
    if u:
        u.exp = 0
        u.level = 1
        db.commit()


def test_add_exp_accumulates(client):
    """经验增量累加：+10 得 10，再 +8 得 18"""
    db = SessionLocal()
    try:
        _reset(db, LEVEL_UID)
        _token_for(db, LEVEL_UID)

        r1 = LevelService.add_exp(db, LEVEL_UID, 10, reason="exam_done")
        assert r1["old_exp"] == 0
        assert r1["new_exp"] == 10
        assert r1["leveled_up"] is False, "10 点经验不应升级（Lv2 门槛 60）"

        r2 = LevelService.add_exp(db, LEVEL_UID, 8, reason="task_done")
        assert r2["old_exp"] == 10 and r2["new_exp"] == 18
        assert _read_exp(LEVEL_UID) == 18, "经验必须已落库，读时零聚合"
    finally:
        _reset(db, LEVEL_UID)
        db.close()


def test_level_up_at_threshold(client):
    """阈值边界：恰好等于 min_exp 升级；差 1 点不升"""
    db = SessionLocal()
    try:
        _reset(db, LEVEL_UID)
        _token_for(db, LEVEL_UID)
        lv2_exp = LEVEL_FALLBACK[1]["min_exp"]  # 60

        # 差 1 点：不升级
        r = LevelService.add_exp(db, LEVEL_UID, lv2_exp - 1, reason="t")
        assert r["new_level"] == 1, f"{lv2_exp - 1} 点不应达到 Lv2"
        assert r["leveled_up"] is False

        # 再补 1 点：恰好等于阈值 → 升级（>= 语义）
        r2 = LevelService.add_exp(db, LEVEL_UID, 1, reason="t")
        assert r2["new_exp"] == lv2_exp
        assert r2["new_level"] == 2, f"经验恰好 {lv2_exp} 应达到 Lv2（>= 语义）"
        assert r2["leveled_up"] is True
        assert r2["levels_gained"] == 1
        # Lv2 升级奖励真实发放（LEVEL_FALLBACK[1].reward_diamond = 2）
        assert r2["reward_diamond"] == LEVEL_FALLBACK[1]["reward_diamond"]
    finally:
        _reset(db, LEVEL_UID)
        db.close()


def test_multi_level_up_merges_rewards(client):
    """一次加大量经验跨多级：中间等级奖励合并发放，余额增量等于应发总额"""
    db = SessionLocal()
    try:
        _reset(db, LEVEL_UID)
        _token_for(db, LEVEL_UID)
        bal0 = _read_balance(LEVEL_UID)

        # 0 + 300 → Lv3（Lv2=60, Lv3=180, Lv4=360）→ 跨 Lv1→Lv3 两级
        r = LevelService.add_exp(db, LEVEL_UID, 300, reason="big")
        assert r["old_level"] == 1 and r["new_level"] == 3, f"应 Lv1→Lv3，实际 {r}"
        assert r["levels_gained"] == 2
        expect = (LEVEL_FALLBACK[1]["reward_diamond"]      # Lv2
                  + LEVEL_FALLBACK[2]["reward_diamond"])   # Lv3
        assert r["reward_diamond"] == expect, f"跨级奖励应合并为 {expect}，实际 {r['reward_diamond']}"
        assert abs(_read_balance(LEVEL_UID) - bal0 - expect) < 1e-6, "钻石增量应与合并奖励一致"
    finally:
        _reset(db, LEVEL_UID)
        db.close()


def test_concurrent_add_exp_no_lost_update(client):
    """并发 add_exp 不丢更新：10 线程各 +10，最终经验必须恰好 100

    若不锁行，「读 exp → 加 delta → 写回」会互相覆盖（经典读改写竞态），
    最终经验会小于 100。本用例是 WITH FOR UPDATE 行锁的回归防线。
    """
    db = SessionLocal()
    try:
        _reset(db, LEVEL_UID)
        _token_for(db, LEVEL_UID)
        errors = []

        def worker():
            s = SessionLocal()
            try:
                LevelService.add_exp(s, LEVEL_UID, 10, reason="concurrent")
            except Exception as exc:  # noqa: BLE001 - 测试收集异常用于断言
                errors.append(repr(exc))
            finally:
                s.close()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发 add_exp 出现异常：{errors[:3]}"
        assert _read_exp(LEVEL_UID) == 100, \
            f"并发 10×(+10) 应得 100，实际 {_read_exp(LEVEL_UID)}（丢更新）"
    finally:
        _reset(db, LEVEL_UID)
        db.close()


def test_level_api_contract(client):
    """GET /api/level 字段契约：等级/进度/下一级/阶梯完整"""
    db = SessionLocal()
    try:
        _reset(db, LEVEL_UID)
        tok = _token_for(db, LEVEL_UID)
        h = {"Authorization": f"Bearer {tok}"}
        LevelService.add_exp(db, LEVEL_UID, 30, reason="t")   # Lv1 区间 (0,60) 内 50%

        r = client.get("/api/level", headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["level"] == 1
        assert j["exp"] == 30
        assert j["next_level"] == 2
        assert j["next_level_exp"] == LEVEL_FALLBACK[1]["min_exp"]
        assert j["exp_to_next"] == LEVEL_FALLBACK[1]["min_exp"] - 30
        assert abs(j["progress_pct"] - 50.0) < 0.01, f"区间进度应为 50%，实际 {j['progress_pct']}"
        assert j["title"] == LEVEL_FALLBACK[0]["title"]
        assert j["is_max"] is False
        assert len(j["ladder"]) == len(LEVEL_FALLBACK), "阶梯表应返回完整等级"
        assert [c["lv"] for c in j["ladder"]] == [c["lv"] for c in LEVEL_FALLBACK]

        # 满级语义：经验推满 → is_max、进度 100、exp_to_next=0
        LevelService.add_exp(db, LEVEL_UID, LEVEL_FALLBACK[-1]["min_exp"], reason="t")
        j2 = client.get("/api/level", headers=h).json()
        assert j2["level"] == len(LEVEL_FALLBACK)
        assert j2["is_max"] is True
        assert j2["progress_pct"] == 100.0
        assert j2["exp_to_next"] == 0
        assert j2["next_level"] is None
    finally:
        _reset(db, LEVEL_UID)
        db.close()


def test_award_event_rules(client):
    """事件与经验规则一致：登记事件按规则加经验、未登记事件不加经验"""
    db = SessionLocal()
    try:
        _reset(db, LEVEL_UID)
        _token_for(db, LEVEL_UID)

        # 登记事件（tag：EVENT_TASK_DONE 规则为 +8）
        res = award(db, LEVEL_UID, EVENT_TASK_DONE)
        assert res["exp_gained"] == 8, f"EVENT_TASK_DONE 应 +8，实际 {res['exp_gained']}"
        assert _read_exp(LEVEL_UID) == 8
        assert "level" in res

        # 未登记事件：不加经验（但仍会跑徽章评估，不报错）
        res2 = award(db, LEVEL_UID, "not_a_registered_event")
        assert res2["exp_gained"] == 0, "未登记事件不应加经验（避免静默虚增）"
        assert _read_exp(LEVEL_UID) == 8, "未登记事件后经验不应变化"

        # extra_exp（专注钟按分钟数追加）参与累加
        res3 = award(db, LEVEL_UID, EVENT_EXAM_DONE, extra_exp=5)
        assert res3["exp_gained"] == 15, f"10(基础)+5(额外) 应为 15，实际 {res3['exp_gained']}"

        # 跨域契约入口与域内入口同源
        res4 = AwardService.award(db, LEVEL_UID, EVENT_EXAM_DONE)
        assert res4["exp_gained"] == 10, "契约入口应与域内入口行为一致"
    finally:
        _reset(db, LEVEL_UID)
        db.close()


def test_ensure_level_config_idempotent(client):
    """等级配置 seed 幂等：重复调用不重复插入，表内容与常量真相源一致"""
    db = SessionLocal()
    try:
        ensure_level_config(db)
        first = db.query(LevelConfig).count()
        assert first >= len(LEVEL_FALLBACK), "seed 后至少应有全部默认等级"

        again = ensure_level_config(db)
        assert again == 0, "二次 seed 应为新增 0 行（幂等）"
        assert db.query(LevelConfig).count() == first

        # 表内数值必须与 LEVEL_FALLBACK 一致（防两处漂移）
        row = db.query(LevelConfig).filter(LevelConfig.lv == 3).first()
        assert row is not None
        assert row.min_exp == LEVEL_FALLBACK[2]["min_exp"]
        assert row.title == LEVEL_FALLBACK[2]["title"]

        # level_for_exp 与表数值自洽
        assert level_for_exp(LEVEL_FALLBACK[2]["min_exp"]) == 3
        assert level_for_exp(LEVEL_FALLBACK[2]["min_exp"] - 1) == 2
    finally:
        db.close()


# ── 回填工具（tools/backfill_level_exp.py）配套校验 ──
# 该脚本只应在线上服务器执行（写生产库），本地不可实跑；故此处做两项零副作用校验：
# ① 经验换算口径与埋点一致；② 脚本引用的模型列名真实存在（列名写错是本脚本最大风险）。

def test_backfill_exp_formula_matches_events():
    """回填经验口径：各事件按 EXP_RULES 累加，专注另按 minutes//10 追加"""
    from app.domains.engagement.services.events import EXP_RULES

    counts = {
        "exam_done": 1, "wrong_mastered": 2, "task_done": 3, "checkin": 4,
        "mood_done": 5, "focus_done": 6, "_focus_minutes": 25,
    }
    expect = (EXP_RULES["exam_done"] * 1 + EXP_RULES["wrong_mastered"] * 2
              + EXP_RULES["task_done"] * 3 + EXP_RULES["checkin"] * 4
              + EXP_RULES["mood_done"] * 5 + EXP_RULES["focus_done"] * 6
              + 25 // 10)
    assert compute_exp(counts) == expect
    # 下划线前缀字段是辅助项，不能被当成事件重复乘 EXP_RULES
    assert compute_exp({"_focus_minutes": 100}) == 10
    assert compute_exp({}) == 0


def test_backfill_tool_column_names_exist():
    """回填脚本引用的所有模型列名必须存在（拼错列名会在线上才炸，这里提前拦住）"""
    from app.models.daily_task import DailyTask
    from app.models.exam import ExamAttempt, WrongRecord
    from app.models.focus import FocusSession
    from app.models.mood import MoodCheckin

    referenced = [
        (ExamAttempt, ["user_id"]),
        (WrongRecord, ["user_id", "is_mastered"]),
        (DailyTask, ["user_id", "status", "task_code"]),
        (MoodCheckin, ["user_id"]),
        (FocusSession, ["user_id", "minutes"]),
    ]
    for model, cols in referenced:
        names = set(model.__table__.columns.keys())
        for col in cols:
            assert col in names, f"{model.__name__} 缺少列 {col}（回填脚本会 SQL 报错）"


def test_perk_texts_all_have_real_landing():
    """等级表里的每条特权文案都必须有**真实落地**（防止再出现「承诺了但看不到」）

    背景：回归时发现 20 条特权（头像框 / 称号专属配色 / 成就墙展示位）当时只被前端
    当文字显示，没有任何按等级生效的视觉效果 —— 用户升到 Lv2 看到「头像框「嫩叶」已解锁」
    却毫无变化。现已补齐落地点，本用例把「文案 ↔ 落地」的对应关系钉死：
    改动 _PERKS 时若新增了没实现的特权类型，这里会立刻失败并提示去补落地点。
    """
    from app.domains.engagement.services.level import _PERKS, MAX_LEVEL

    # 已实现落地的特权类型 -> 落地点说明（新增类型时必须同步实现并登记到这里）
    LANDED = {
        "基础徽标": "顶栏 Lv.N 徽标（App.vue .lv-badge）",
        "称号专属配色": "levelHue() 经 --lv-h 下发，徽标/hero/进度条/特权条共用",
        "头像框": "levelFrameTier() 经 --lv-tier 控制 .lv-frame 边框与光晕",
        "传奇头像框": "同上（Lv20 用「传奇」前缀标识最高档，仍走 levelFrameTier=10）",
        "成就墙展示位": "BadgesView .lv-showcase 等级展示卡",
    }

    def classify(perk: str) -> str:
        """把一条特权文案归类到已落地的类型；认不出就返回原文（触发失败）"""
        for key in LANDED:
            if perk == key or perk.startswith(key):
                return key
        return perk

    assert len(_PERKS) == MAX_LEVEL, f"特权条数应与等级数一致：{len(_PERKS)} != {MAX_LEVEL}"

    unknown = sorted({p for p in _PERKS if classify(p) not in LANDED})
    assert not unknown, (
        f"以下特权文案没有对应的已落地实现，会变成「承诺了但看不到」：{unknown}。"
        f"请先实现视觉落地点，再加入 LANDED 映射（{list(LANDED)}）")


def test_frame_tier_matches_frame_perk_levels():
    """头像框档位必须与等级表中「头像框「X」」所在的等级一一对应（10 个框 ↔ 10 个档）

    前端 levelFrameTier = Lv2 起 floor(lv/2)（上限 10）；后端特权文案里带「头像框」的
    等级是 2/4/6/…/20。两者若漂移，会出现「文案说解锁了第 N 个框，实际档位不是 N」。
    """
    from app.domains.engagement.services.level import _PERKS

    frame_levels = [i + 1 for i, p in enumerate(_PERKS) if "头像框" in p]
    assert frame_levels == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20], (
        f"头像框等级应为 2..20 的偶数级，实际 {frame_levels}")

    def js_frame_tier(lv: int) -> int:
        """与 web/src/logic/level.js 的 levelFrameTier() 同口径"""
        return 0 if lv < 2 else min(10, lv // 2)

    tiers = [js_frame_tier(lv) for lv in frame_levels]
    assert tiers == list(range(1, 11)), f"档位应为 1..10，实际 {tiers}"
    assert js_frame_tier(1) == 0, "Lv1 尚未解锁任何头像框，档位应为 0"
