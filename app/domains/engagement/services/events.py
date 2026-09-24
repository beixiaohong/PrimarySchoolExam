"""行为事件统一入口（新功能 B 成就 / C 等级共同收敛层）

设计动机
--------
B（成就）与 C（等级）都以「用户做了一件事」为触发源，若各自在业务写操作后分别埋点，
会出现两个问题：① 同一行为要改两个调用点，新增激励维度（宠物币/积分）就要再改一遍；
② 事件名分散在多处字符串字面量里，极易拼写漂移（写错的事件名不报错、静默不授予）。

因此把「行为事件」抽象成本模块：**事件名与经验规则集中在此**，业务侧只需
`award(db, uid, EVENT_X)` 一次调用，内部按固定顺序驱动各激励子系统。

事件名是单一真相源
------------------
`services/achievement.py` 的 `BADGE_RULES` 不再自己定义事件常量，改为从本模块导入，
保证「徽章触发事件」与「经验规则事件」用同一套字面量。

铁律合规
--------
- 纯 DB 操作，无 AI/HTTP/SMTP 等外部阻塞调用；
- 埋点调用点均在业务写操作 `db.commit()` **之后**，不延长原事务持锁时间；
- 内部逐段 try/except：任一激励子系统失败都不影响主业务流程（奖励可丢，业务不可挂）。
"""
import logging

logger = logging.getLogger("engagement.events")

# ── 行为事件名（单一真相源）──────────────────────────────────────────────
# 学习类
EVENT_EXAM_DONE = "exam_done"                    # 交卷（assessment）
EVENT_WRONG_MASTERED = "wrong_mastered"          # 错题标记已掌握（assessment）
EVENT_VOCAB_MASTERED = "vocab_mastered"          # 掌握单词（engine）
EVENT_CLASSICAL_MASTERED = "classical_met"       # 掌握古诗文（content）
# 坚持类
EVENT_TASK_DONE = "task_done"                    # 每日任务完成（engagement）
EVENT_MOOD_DONE = "mood_done"                    # 心情打卡（engagement）
EVENT_CHECKIN = "checkin"                        # 每日签到（engagement，新功能 A/C）
EVENT_FOCUS_DONE = "focus_done"                  # 完成一次番茄专注（engagement）
# 社交 / 目标类
EVENT_TEACH_PASSED = "teach_passed"              # 讲题通过（engagement）
EVENT_CHALLENGE_DONE = "challenge_done"          # 挑战赛（engagement）
EVENT_GOAL_DONE = "goal_done"                    # 目标达成（engagement / engine）

# ── 经验规则（event -> 基础经验值）──────────────────────────────────────
# 未登记的事件经验为 0（仍会走徽章评估，只是不加经验），因此新增事件时
# 若希望给经验，必须在此显式登记——避免"以为加了经验其实没加"的静默失效。
EXP_RULES = {
    EVENT_EXAM_DONE: 10,          # 完整做完一套卷
    EVENT_WRONG_MASTERED: 5,      # 攻克一道错题
    EVENT_TASK_DONE: 8,           # 完成一项每日任务
    EVENT_MOOD_DONE: 3,           # 心情打卡
    EVENT_CHECKIN: 5,             # 每日签到
    EVENT_FOCUS_DONE: 4,          # 专注钟（另有按分钟数的贡献，见 extra_exp）
    EVENT_VOCAB_MASTERED: 3,      # 掌握一个单词
    EVENT_CLASSICAL_MASTERED: 8,  # 背诵一篇古诗文
    EVENT_TEACH_PASSED: 10,       # 讲题通过
    EVENT_CHALLENGE_DONE: 6,      # 完成一次挑战
    EVENT_GOAL_DONE: 12,          # 达成学习目标
}


def award(db, user_id: str, event: str, extra_exp: int = 0) -> dict:
    """一次行为事件的统一奖励入口：加经验（可能升级）+ 评估徽章。

    参数
    ----
    db        : 调用方会话（调用点须在业务 `commit()` 之后，避免延长原事务持锁）
    user_id   : 业务用户标识（users.user_id）
    event     : 事件名，取本模块 EVENT_* 常量
    extra_exp : 额外经验（如专注钟按分钟数追加），默认 0

    返回
    ----
    {"event", "exp_gained", "level": {...}|None, "new_badges": [code, ...]}
    任一子系统异常都会被吞掉并记日志，返回值可能是**部分结果**——调用方不应依赖它
    做业务判断，它只用于日志/调试与测试断言。

    顺序说明：先加经验（纯 DB、可能发升级钻石），再评估徽章。两者互相独立，
    后者失败不影响前者已提交的结果。
    """
    result = {"event": event, "exp_gained": 0, "level": None, "new_badges": []}

    # 1) 经验与升级（含升级钻石奖励）
    delta = int(EXP_RULES.get(event, 0)) + int(extra_exp or 0)
    if delta > 0:
        try:
            from app.domains.engagement.services.level import add_exp
            info = add_exp(db, user_id, delta, reason=event)
            result["exp_gained"] = delta
            result["level"] = info
        except Exception:
            logger.warning("加经验失败 user=%s event=%s delta=%s", user_id, event, delta,
                           exc_info=True)

    # 2) 徽章实时评估（事件驱动，只评估该事件的徽章）
    try:
        from app.domains.engagement.services.achievement import try_grant
        result["new_badges"] = try_grant(db, user_id, event) or []
    except Exception:
        logger.warning("徽章评估失败 user=%s event=%s", user_id, event, exc_info=True)

    return result
