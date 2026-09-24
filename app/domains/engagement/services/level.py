"""等级 / 成长体系服务（新功能 C，2026Q4）

设计要点
--------
1. **经验增量落库，读时零聚合**。`users.exp` 由 `add_exp()` 在行为发生时累加并落库，
   `get_level_info()` 只读 `users.exp` 一个字段——不做「交卷数 + 正确率 + 专注时长 + 错题」
   的实时多表聚合（那会让等级页每次打开都付 N 条聚合查询，与 B 修掉的短板同类）。
2. **等级由 exp 反算，`users.level` 只是冗余缓存**。展示等级一律用 `level_for_exp(exp)`，
   因此列值脏/NULL/历史不一致都不会显示错误等级（存量用户补列后即自愈）。
3. **`add_exp` 带 `WITH FOR UPDATE` 行锁**（复用钻石锁范式）。并发场景真实存在：
   孩子交卷（+10）与完成任务（+8）同时发生，若不锁行，「读 exp → 加 delta → 写回」
   的读改写竞态会丢更新（后写覆盖先写）。
4. **等级阶梯单一真相源**：默认 20 级由 `LEVEL_FALLBACK` 定义、迁移 `080` 幂等 seed 进
   `level_config` 表；运行期优先读表（支持后台调参），表为空时回落到常量（首次部署兜底）。

铁律合规
--------
- 纯 DB 操作，无外部/AI 调用；
- `add_exp` 先 `commit()` 释放 `users` 行锁，再走跨域发升级钻石——不在持锁期间调用其它域。
"""
import logging

from sqlalchemy.orm import Session

from app.domains.commerce.contracts import DiamondService
from app.models.level import LevelConfig
from app.models.user import User

logger = logging.getLogger("engagement.level")

# 等级上限（新增等级时同步扩 _TITLES/_PERKS/_REWARDS 三个列表）
MAX_LEVEL = 20

# 称号：20 级，由低到高
_TITLES = (
    "好奇幼苗", "勤学小芽", "进步小星", "努力小将", "知识小探",
    "答题小能手", "学习小达人", "智慧小先锋", "双科小标兵", "三科小明星",
    "解题小高手", "知识小博士", "学习小超人", "智慧小导师", "学霸小榜样",
    "全能小冠军", "闪耀小学者", "传奇小院士", "智慧领航员", "智学之光",
)

# 特权说明：全部为**前端按 lv 可渲染**的展示类权益（头像框 / 展示位 / 称号配色），
# 不含需要改造 AI 链路的额度承诺，避免出现"写了但没实现"的权益。
_PERKS = (
    "基础徽标", "头像框「青苗」", "称号专属配色", "头像框「嫩叶」", "成就墙展示位",
    "头像框「向阳」", "称号专属配色", "头像框「星辰」", "成就墙展示位", "头像框「皓月」",
    "称号专属配色", "头像框「流云」", "成就墙展示位", "头像框「苍穹」", "称号专属配色",
    "头像框「星辉」", "成就墙展示位", "头像框「冠军金」", "称号专属配色", "传奇头像框「智学之光」",
)

# 升级奖励钻石（真实发放，经 commerce.contracts.DiamondService.grant）
_REWARDS = (
    0, 2, 3, 3, 5,
    5, 6, 6, 8, 10,
    10, 12, 12, 15, 15,
    18, 18, 20, 25, 50,
)

# 默认等级阶梯（单一真相源；迁移 080 按此 seed，服务层在表为空时回落到此）
# min_exp = 30 * (lv-1) * lv → Lv1=0 / Lv2=60 / Lv3=180 / Lv10=2700 / Lv20=11400
LEVEL_FALLBACK = tuple(
    {
        "lv": i + 1,
        "min_exp": 30 * i * (i + 1),
        "title": _TITLES[i],
        "perk": _PERKS[i],
        "reward_diamond": _REWARDS[i],
    }
    for i in range(MAX_LEVEL)
)


def level_for_exp(exp: int, ladder=None) -> int:
    """按累计经验反算等级（纯函数，无 DB 依赖，便于测试与复用）。

    边界语义：经验**恰好等于**某级 `min_exp` 即视为达到该级（`>=`，不是 `>`）。
    """
    rows = ladder if ladder else LEVEL_FALLBACK
    exp = int(exp or 0)
    level = 1
    for cfg in sorted(rows, key=lambda c: (int(c["min_exp"]), int(c["lv"]))):
        if exp >= int(cfg["min_exp"]):
            level = int(cfg["lv"])
        else:
            break
    return level


def _ladder(db: Session) -> list:
    """读取等级阶梯：优先用 level_config 表（支持后台调参），表为空/不可用时回落常量。"""
    try:
        rows = (db.query(LevelConfig)
                .filter(LevelConfig.is_active.is_(True))
                .order_by(LevelConfig.lv).all())
    except Exception:
        rows = []
    if not rows:
        return [dict(c) for c in LEVEL_FALLBACK]
    return [
        {"lv": int(r.lv), "min_exp": int(r.min_exp), "title": r.title or "",
         "perk": r.perk or "", "reward_diamond": int(r.reward_diamond or 0)}
        for r in rows
    ]


def ensure_level_config(db: Session) -> int:
    """幂等补齐等级配置：按 lv 增量插入缺失等级，返回新增行数。

    用「按 lv 增量补齐」而非「表为空才 seed」——这样后续版本扩到 25 级时，
    新等级会在下次启动自动补进表里，且不会覆盖后台已调过的旧等级数值。
    """
    existing = {int(r[0]) for r in db.query(LevelConfig.lv).all()}
    added = 0
    for cfg in LEVEL_FALLBACK:
        if int(cfg["lv"]) in existing:
            continue
        db.add(LevelConfig(**cfg))
        added += 1
    if added:
        db.commit()
    return added


def add_exp(db: Session, user_id: str, delta: int, reason: str = "") -> dict:
    """为某次行为累加经验，必要时提升等级并发放升级奖励（并发安全）。

    返回
    ----
    {"user_id","delta","reason","old_exp","new_exp","old_level","new_level",
     "leveled_up","levels_gained","reward_diamond"}
    用户不存在或 delta<=0 时返回当前值且 leveled_up=False（不抛异常——激励不该打断业务）。

    并发安全：SELECT ... FOR UPDATE 锁住 users 行，避免并发读改写覆盖丢经验。
    """
    delta = int(delta or 0)
    # 行锁读改写：并发 add_exp（同时交卷 + 完成任务）必须串行，否则丢更新
    user = db.query(User).filter(User.user_id == user_id).with_for_update().first()
    if not user:
        return {"user_id": user_id, "delta": 0, "reason": reason, "old_exp": 0, "new_exp": 0,
                "old_level": 1, "new_level": 1, "leveled_up": False, "levels_gained": 0,
                "reward_diamond": 0}
    if delta <= 0:
        exp = int(user.exp or 0)
        lv = level_for_exp(exp)
        return {"user_id": user_id, "delta": 0, "reason": reason, "old_exp": exp, "new_exp": exp,
                "old_level": lv, "new_level": lv, "leveled_up": False, "levels_gained": 0,
                "reward_diamond": 0}

    ladder = _ladder(db)
    old_exp = int(user.exp or 0)
    new_exp = old_exp + delta
    old_level = level_for_exp(old_exp, ladder)
    new_level = level_for_exp(new_exp, ladder)

    user.exp = new_exp
    user.level = new_level        # 冗余缓存；展示以 exp 反算为准
    db.commit()                   # 先提交，释放 users 行锁，再做跨域发奖

    reward = 0
    if new_level > old_level:
        # 一次加大量经验可能跨多级 → 奖励合并发放（不漏发中间等级）
        reward = sum(int(c["reward_diamond"]) for c in ladder
                     if old_level < int(c["lv"]) <= new_level)
        if reward > 0:
            try:
                DiamondService.grant(db, user_id, float(reward), biz="level_up")
            except Exception:
                # 发奖失败不回滚经验（经验已落库），仅记日志；返回值置 0 以免调用方误判已发
                logger.warning("升级奖励发放失败 user=%s lv=%s->%s reward=%s",
                               user_id, old_level, new_level, reward, exc_info=True)
                reward = 0

    return {
        "user_id": user_id,
        "delta": delta,
        "reason": reason,
        "old_exp": old_exp,
        "new_exp": new_exp,
        "old_level": old_level,
        "new_level": new_level,
        "leveled_up": new_level > old_level,
        "levels_gained": max(0, new_level - old_level),
        "reward_diamond": reward,
    }


def get_level_info(db: Session, user_id: str) -> dict:
    """等级详情：当前等级/经验/称号/特权 + 距下一级进度 + 完整阶梯表。

    进度语义：`progress_pct` 为**当前等级区间内**的完成百分比（0~100），
    区间下界为本级 min_exp、上界为下一级 min_exp；满级固定 100。
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    exp = int(user.exp or 0) if user else 0
    ladder = _ladder(db)
    level = level_for_exp(exp, ladder)

    cur = next((c for c in ladder if c["lv"] == level), ladder[0])
    nxt = next((c for c in ladder if c["lv"] == level + 1), None)
    if nxt:
        span = int(nxt["min_exp"]) - int(cur["min_exp"])
        done = exp - int(cur["min_exp"])
        pct = round(min(100.0, max(0.0, done * 100.0 / span)), 1) if span > 0 else 100.0
        next_exp = int(nxt["min_exp"])
    else:
        pct, next_exp = 100.0, int(cur["min_exp"])

    return {
        "user_id": user_id,
        "level": level,
        "exp": exp,
        "title": cur["title"],
        "perk": cur["perk"],
        "level_min_exp": int(cur["min_exp"]),
        "next_level": int(nxt["lv"]) if nxt else None,
        "next_title": nxt["title"] if nxt else None,
        "next_level_exp": next_exp,
        "exp_to_next": max(0, next_exp - exp) if nxt else 0,
        "progress_pct": pct,
        "is_max": nxt is None,
        "max_level": MAX_LEVEL,
        "reward_diamond": int(cur["reward_diamond"]),
        "ladder": [
            {"lv": c["lv"], "min_exp": c["min_exp"], "title": c["title"],
             "perk": c["perk"], "reward_diamond": c["reward_diamond"]}
            for c in ladder
        ],
    }
