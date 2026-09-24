"""四项新功能（A 签到 / B 成就 / C 等级 / D 收藏）端到端联动回归

为什么需要这一层：单元测试各自只覆盖本模块内部逻辑，**跨模块串联**才是回归最容易
出问题的地方（写入路径与读回路径由不同代码负责、跨域调用要过 contracts、迁移时序等）。
本文件把「真实 HTTP 调用 → 落库 → 另一接口读回」串起来验收，共 8 例：

1. 签到 → `users.exp` 恰好 +5 → `GET /api/level` 与库一致且等级由 exp 反算；
2. 签到幂等：重复 POST 不得重复加经验；
3. `GET /api/level` 进度字段自洽（exp + exp_to_next == next_level_exp）；
4. 等级阶梯自洽：20 级连续、min_exp 严格单调、Lv1=0、边界语义 `>=`、`level_config` 已 seed；
5. 徽章接口结构与**签到事件实时解锁**（踩过前后端契约坑，故带 `?user_id=`）；
6. 收藏夹闭环：加 → 列表可见 → 删 → 列表消失；
7. **迁移幂等**：`run_migrations()` 重复执行不改变 `level_config` 行数
   （deploy.sh 每次重启都会触发迁移，这条是上线安全阀）；
8. **存量脏值兼容**：`exp`/`level` 为 NULL 或 `level` 为脏值时，展示一律由 exp 反算自愈
   （补列后未回填的历史用户不能被打挂）。

注意：读断言一律用**独立 SessionLocal**——MySQL REPEATABLE READ 下长会话快照会冻结，
读不到接口内部新提交的值（本项目测试已知陷阱）。
"""
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.domains.engagement.services.events import EVENT_CHECKIN, EXP_RULES
from app.domains.engagement.services.level import MAX_LEVEL, level_for_exp
from app.models.favorite import UserFavorite
from app.models.level import LevelConfig
from app.models.user import User

UID = "smoke_e2e_uid"


def _reset_user(uid: str) -> str:
    """建/重置专属用户（exp=0、level=1）并签发 token，返回 token"""
    db: Session = SessionLocal()
    try:
        u = db.query(User).filter(User.user_id == uid).first()
        if not u:
            u = User(user_id=uid, nickname=uid, grade=6, subject="英语")
            db.add(u)
        u.token = secrets.token_urlsafe(32)
        u.token_expires_at = datetime.now() + timedelta(hours=24)
        u.exp = 0
        u.level = 1
        db.commit()
        return u.token
    finally:
        db.close()


def _fresh_exp(uid: str) -> int:
    """独立会话读最新已提交的 exp（规避 REPEATABLE READ 快照冻结）"""
    db: Session = SessionLocal()
    try:
        u = db.query(User).filter(User.user_id == uid).first()
        return int(u.exp or 0) if u else 0
    finally:
        db.close()


def _cleanup_fav(uid: str):
    db: Session = SessionLocal()
    try:
        db.query(UserFavorite).filter(UserFavorite.user_id == uid).delete()
        db.commit()
    finally:
        db.close()


# ── 1. 签到 → 经验（端到端串联：HTTP 写 → 库 → HTTP 读）──
def test_e2e_checkin_increases_exp_then_level_api(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}
    assert _fresh_exp(UID) == 0, "前置：exp 应被重置为 0"

    r = client.post("/api/checkin", headers=h)
    assert r.status_code == 200, r.text

    gained = _fresh_exp(UID)
    assert gained == EXP_RULES[EVENT_CHECKIN], (
        f"签到应恰好加 {EXP_RULES[EVENT_CHECKIN]} 经验，实际 {gained}")

    # GET /api/level 必须与库里 exp 一致，且等级由 exp 反算
    r2 = client.get("/api/level", headers=h)
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert d["exp"] == gained, f"接口 exp={d['exp']} 与库 {gained} 不一致"
    assert d["level"] == level_for_exp(gained), "level 应为 exp 反算结果"
    assert d["max_level"] == MAX_LEVEL


# ── 2. 签到幂等：重复 POST 不得重复加经验 ──
def test_e2e_checkin_idempotent_no_double_exp(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}

    client.post("/api/checkin", headers=h)
    once = _fresh_exp(UID)
    client.post("/api/checkin", headers=h)
    twice = _fresh_exp(UID)
    assert once == twice, f"重复签到不应再加经验：{once} → {twice}"


# ── 3. 级别 API 的进度字段自洽性 ──
def test_e2e_level_api_progress_consistent(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}
    d = client.get("/api/level", headers=h).json()

    assert 0.0 <= d["progress_pct"] <= 100.0, f"progress_pct 越界: {d['progress_pct']}"
    if not d["is_max"]:
        assert d["exp"] + d["exp_to_next"] == d["next_level_exp"], (
            "exp + exp_to_next 应等于 next_level_exp")
        assert d["next_level"] == d["level"] + 1, "next_level 应为当前级 +1"
        assert d["exp_to_next"] > 0, "非满级时 exp_to_next 应 > 0"
    else:
        assert d["progress_pct"] == 100.0


# ── 4. 等级阶梯自洽（表 seed 正确、单调、连续、边界）──
def test_e2e_level_ladder_self_consistent(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}
    ladder = client.get("/api/level", headers=h).json()["ladder"]

    assert len(ladder) == MAX_LEVEL, f"阶梯应 {MAX_LEVEL} 级，实际 {len(ladder)}"
    assert [c["lv"] for c in ladder] == list(range(1, MAX_LEVEL + 1)), "lv 应 1..N 连续"
    assert ladder[0]["min_exp"] == 0, "Lv1 门槛应为 0"
    mins = [c["min_exp"] for c in ladder]
    assert mins == sorted(mins) and len(set(mins)) == len(mins), "min_exp 应严格递增"
    for c in ladder:
        assert c["title"], f"Lv{c['lv']} 缺称号"
        assert c["perk"], f"Lv{c['lv']} 缺特权"

    # 边界语义（>=）：恰好等于阈值即达该级，差 1 仍为上一级
    for c in ladder[1:]:
        assert level_for_exp(c["min_exp"]) == c["lv"], f"恰好 {c['min_exp']} 应为 Lv{c['lv']}"
        assert level_for_exp(c["min_exp"] - 1) == c["lv"] - 1, f"{c['min_exp']-1} 应为 Lv{c['lv']-1}"

    # level_config 表实际 seed 行数
    db: Session = SessionLocal()
    try:
        n = db.query(LevelConfig).count()
        assert n >= MAX_LEVEL, f"level_config 应至少 {MAX_LEVEL} 行，实际 {n}"
    finally:
        db.close()


# ── 5. 徽章接口结构 + 签到事件实时解锁 ──
def test_e2e_badges_structure_and_realtime(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}

    # 契约：GET /api/badges?user_id=xxx（前端 logic/badges.js 亦如此调用）
    r = client.get(f"/api/badges?user_id={UID}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "items" in d and isinstance(d["items"], list), "应返回 items 列表"
    for it in d["items"]:
        assert "progress" in it, f"徽章 {it.get('code')} 缺 progress"
        p = it["progress"]
        assert set(("current", "target", "pct")) <= set(p), f"progress 字段不全: {p}"
        assert 0 <= p["pct"] <= 100, f"progress.pct 越界: {p['pct']}"

    # 签到后：与签到相关的徽章进度应已推进（current >= 1）
    client.post("/api/checkin", headers=h)
    d2 = client.get(f"/api/badges?user_id={UID}", headers=h).json()
    checkin_like = [it for it in d2["items"]
                    if "checkin" in str(it.get("code", "")).lower()
                    or "签到" in str(it.get("name", ""))]
    if checkin_like:
        assert any(it["progress"]["current"] >= 1 for it in checkin_like), (
            "签到后相关徽章进度未推进（实时授予链路可能断了）")


# ── 6. 收藏夹闭环：加 → 列表可见 → 删 → 列表消失 ──
def test_e2e_favorites_roundtrip(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}
    _cleanup_fav(UID)

    r = client.post("/api/favorites", headers=h,
                    json={"item_type": "paper", "item_id": "smoke-e2e-1", "title": "冒烟卷"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]

    lst = client.get("/api/favorites", headers=h).json()
    items = lst["items"] if isinstance(lst, dict) and "items" in lst else lst
    assert any(x["id"] == fid for x in items), "收藏后列表应可见"

    rd = client.delete(f"/api/favorites/{fid}", headers=h)
    assert rd.status_code == 200, rd.text

    lst2 = client.get("/api/favorites", headers=h).json()
    items2 = lst2["items"] if isinstance(lst2, dict) and "items" in lst2 else lst2
    assert not any(x["id"] == fid for x in items2), "删除后列表不应可见"
    _cleanup_fav(UID)


# ── 7. 迁移幂等：deploy.sh 每次重启都会 run_migrations，重复跑必须无副作用 ──
def test_e2e_migration_idempotent(client):
    from app.migrations.runner import run_migrations

    db: Session = SessionLocal()
    try:
        before = db.query(LevelConfig).count()
    finally:
        db.close()

    run_migrations()   # 第二次执行（client fixture 已跑过一次）

    db = SessionLocal()
    try:
        after = db.query(LevelConfig).count()
    finally:
        db.close()
    assert after == before, f"重复迁移不应改变 level_config 行数：{before} → {after}"


# ── 8. 存量用户脏值兼容：补列后 exp/level 可能为 NULL 或脏，展示须自愈 ──
def test_e2e_legacy_dirty_values_self_heal(client):
    tok = _reset_user(UID)
    h = {"Authorization": f"Bearer {tok}"}

    db: Session = SessionLocal()
    try:
        u = db.query(User).filter(User.user_id == UID).first()
        u.exp = None       # 场景 A：补列后未回填
        u.level = None
        db.commit()
    finally:
        db.close()

    r = client.get("/api/level", headers=h)
    assert r.status_code == 200, f"exp/level 为 NULL 时不应报错：{r.text}"
    d = r.json()
    assert d["exp"] == 0 and d["level"] == 1, f"NULL 应回落为 exp=0/Lv1，实际 {d['exp']}/{d['level']}"
    assert d["progress_pct"] >= 0.0

    # 场景 B：level 列被写成脏值（99），但 exp=0 → 展示应以 exp 反算为准
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.user_id == UID).first()
        u.exp = 0
        u.level = 99
        db.commit()
    finally:
        db.close()

    d2 = client.get("/api/level", headers=h).json()
    assert d2["level"] == 1, f"level 列脏值不应影响展示（应由 exp 反算）：实际 {d2['level']}"
