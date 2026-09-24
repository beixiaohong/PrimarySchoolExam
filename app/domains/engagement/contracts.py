"""D5 激励与成长域对外契约（S1-R Step 4 落地）

本模块是该域唯一允许被其它域 import 的入口（`.importlinter` 域独立契约强制）。

对外能力
- `PetService.grant_coins(db, uid, amount, reason)`：发金币，收口此前 12 处 `_grant_coins` 直呼
  （assessment 的 ai_quiz / dictation / teach / exam.attempts×2 / exam.wrong，engine 的
  study.errors / study.practice，以及域内 focus / tasks.daily / tasks.makeup_service /
  tasks.custom）。其中 `tasks/custom.py` 原写作 `from app.pet import _grant_coins`（三点相对
  层级错误、恒 ImportError 被外层 try/except 吞掉 → 家长确认自定义任务的 +5 金币从未发放），
  本次随契约收口一并修正为可用路径，属计划 D5 提交已承诺的缺陷修复。
- `PetService.balance(db, uid)`：金币余额（收口 platform/assistant 对 `_balance` 的直连）。
- `GrowthTreeService.score(db, uid)`：孩子成长值（收口 platform/assistant 对 `compute_tree_score` 的直连）。
- `TaskService.daily_quota(db, uid, key)` / `TaskService.study_flags(db, uid)`：家长任务设置读取
  （收口 content/classical.recite、engine/vocab、engine/study.dashboard 对 `get_daily_quota`、
  `_load_study_flags` 的直连）。
- `TaskService.pending_task_confirms(db, uid)` / `TaskService.pending_makeups(db, uid)`：家长待办计数
  （供 family/parent.py 的 `/api/parent/notices` 聚合家长待办角标；`pending_makeups` 内部复用
  `makeup_service.list_pending_makeup` 保证与 `/api/tasks/makeup/pending` 返回条数恒等，family 不
  直接 import engagement 内部，避免破域独立契约）。
- `AchievementService.try_grant(db, uid, event)`：事件驱动的成就实时授予（新功能 B）。
  收口 assessment（交卷 exam_done / 错题掌握 wrong_mastered）等跨域埋点，让徽章在行为发生时
  即时解锁而非等用户下次访问徽章墙；纯 DB 无外部调用，调用方须在写操作 commit 后调用。
- `AwardService.award(db, uid, event, extra_exp=0)`：**行为事件统一奖励入口**（新功能 C 引入）。
  一次调用同时驱动经验（C 等级，可能升级并发升级钻石）与徽章（B 成就）。各域埋点应优先用它
  而非单独调 try_grant——新增激励维度时无需再改各调用点。返回
  `{"event","exp_gained","level","new_badges"}`，内部逐段 try/except，不影响主业务流程。
- `LevelService.info(db, uid)` / `LevelService.add_exp(db, uid, delta, reason)`：等级/经验读写
  （C）。`add_exp` 带行锁并发安全，供跨域补加经验；`info` 为只读详情。
- `EVENT_*` 事件名常量再导出（值定义在 `services/events.py`）：跨域埋点传参用常量而非
  字符串字面量，避免拼写漂移导致静默不授予。
- 其余为存量符号的显式再导出（延迟解析，名字与实现一致以便逐步替换），带下划线者
  属域内私有 helper 被跨域引用形成的契约债，S1.5 实现内聚后去除。

文档 02 所列 `TaskService.ensure_today(uid)`、`RewardService.grant(uid, type, amount)`
为 M0「任务与学习路径联动」的目标接口，现无同名实现（今日任务由 `/api/tasks/today` 路由内部
生成），本期不新建；落地后在此登记。
"""
from app.domains._lazy import resolve

_EXPORTS = {
    "compute_tree_score": ("app.domains.engagement.routers.tree", "compute_tree_score"),
    "get_daily_quota": ("app.domains.engagement.routers.tasks", "get_daily_quota"),
    "_load_study_flags": ("app.domains.engagement.routers.tasks", "_load_study_flags"),
    # 存量私有符号（契约债，逐步由 PetService 替换）
    "_grant_coins": ("app.domains.engagement.routers.pet", "_grant_coins"),
    "_balance": ("app.domains.engagement.routers.pet", "_balance"),
    # ── 行为事件名（新功能 C）：单一真相源在 services/events.py ──
    # 跨域埋点用常量而非字面量，避免写错事件名静默不授予（延迟解析，模块 __getattr__ 支持
    # `from ...contracts import EVENT_EXAM_DONE` 形态）。
    "EVENT_EXAM_DONE": ("app.domains.engagement.services.events", "EVENT_EXAM_DONE"),
    "EVENT_WRONG_MASTERED": ("app.domains.engagement.services.events", "EVENT_WRONG_MASTERED"),
    "EVENT_TASK_DONE": ("app.domains.engagement.services.events", "EVENT_TASK_DONE"),
    "EVENT_MOOD_DONE": ("app.domains.engagement.services.events", "EVENT_MOOD_DONE"),
    "EVENT_CHECKIN": ("app.domains.engagement.services.events", "EVENT_CHECKIN"),
    "EVENT_FOCUS_DONE": ("app.domains.engagement.services.events", "EVENT_FOCUS_DONE"),
    "EVENT_VOCAB_MASTERED": ("app.domains.engagement.services.events", "EVENT_VOCAB_MASTERED"),
    "EVENT_CLASSICAL_MASTERED": ("app.domains.engagement.services.events", "EVENT_CLASSICAL_MASTERED"),
    "EVENT_TEACH_PASSED": ("app.domains.engagement.services.events", "EVENT_TEACH_PASSED"),
    "EVENT_CHALLENGE_DONE": ("app.domains.engagement.services.events", "EVENT_CHALLENGE_DONE"),
    "EVENT_GOAL_DONE": ("app.domains.engagement.services.events", "EVENT_GOAL_DONE"),
}

__all__ = ("PetService", "GrowthTreeService", "TaskService", "MakeupService",
           "AchievementService", "AwardService", "LevelService") + tuple(_EXPORTS)


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)


class PetService:
    """金币（宠物体系货币）对外唯一入口。

    金币余额由 `coin_ledger` 流水累加得出，无独立余额表；`grant_coins` 只登记流水，
    提交事务由调用方负责（与收口前行为一致）。
    """

    @staticmethod
    def grant_coins(db, uid: str, amount: int, reason: str) -> None:
        """发金币（amount=0 或 uid 为空时静默跳过），reason 为业务归因"""
        from app.domains.engagement.routers.pet import _grant_coins
        return _grant_coins(db, uid, amount, reason)

    @staticmethod
    def balance(db, uid: str) -> int:
        """金币余额（流水求和）"""
        from app.domains.engagement.routers.pet import _balance
        return _balance(db, uid)


class GrowthTreeService:
    """成长树对外入口。"""

    @staticmethod
    def score(db, uid: str) -> int:
        """孩子成长值（成长树接口与 AI 学习助手画像共用口径）"""
        from app.domains.engagement.routers.tree import compute_tree_score
        return compute_tree_score(db, uid)


class TaskService:
    """每日任务与家长任务设置对外入口。"""

    @staticmethod
    def daily_quota(db, uid: str, key: str) -> int:
        """读家长配置的每日额度，未配置返回默认值"""
        from app.domains.engagement.routers.tasks import get_daily_quota
        return get_daily_quota(db, uid, key)

    @staticmethod
    def study_flags(db, uid: str) -> dict:
        """读学习开关（include_next 预习下学期 / sync_mode 课堂同步 / xsc_bridge 小升初衔接）"""
        from app.domains.engagement.routers.tasks import _load_study_flags
        return _load_study_flags(db, uid)

    @staticmethod
    def pending_task_confirms(db, uid: str) -> int:
        """今日待家长确认的手动任务数。

        口径：DailyTask.user_id==uid AND task_date==today AND status=='pending_confirm' AND manual==True，
        与家长面板「今日任务确认」列表逐条一致（列表按 t.manual && t.status=='pending_confirm' 渲染）。
        必须限定 task_date==today，否则角标会含历史遗留而列表不显示，两者对不上。
        """
        from datetime import date
        from app.models.daily_task import DailyTask
        return db.query(DailyTask).filter(
            DailyTask.user_id == uid,
            DailyTask.task_date == date.today(),
            DailyTask.status == "pending_confirm",
            DailyTask.manual == True,  # noqa: E712
        ).count()

    @staticmethod
    def pending_makeups(db, uid: str) -> int:
        """待家长确认的补签申请数（复用 list_pending_makeup，与 /api/tasks/makeup/pending 条数恒等）"""
        from app.domains.engagement.routers.tasks.makeup_service import list_pending_makeup
        return len(list_pending_makeup(db, uid))


class AchievementService:
    """成就徽章对外唯一入口（新功能 B）。

    实时授予：由各域在自己的写操作 commit 之后调用，只评估与该事件相关的徽章，
    返回本次新解锁的 code 列表（调用方可用于前端 Toast）。失败应由调用方 try/except 兜底，
    成就授予不得影响主业务流程。
    """

    @staticmethod
    def try_grant(db, uid: str, event: str = None) -> list:
        """评估并授予徽章，返回新解锁 code 列表。

        event 取值见 `services/achievement.py` 的 EVENT_* 常量（如 "exam_done"、
        "wrong_mastered"）；传 None 表示兜底全量评估。
        """
        from app.domains.engagement.services.achievement import try_grant
        return try_grant(db, uid, event)


class AwardService:
    """行为事件统一奖励入口（新功能 C）。

    为什么要有这一层：B（徽章）与 C（等级）都以「用户做了一件事」为触发源。若各域分别调
    `AchievementService.try_grant` 与 `LevelService.add_exp`，则① 同一行为要改两个调用点，
    ② 将来新增激励维度（宠物币/积分）还要再改一遍所有埋点。统一为一次 `award()` 调用后，
    各域埋点不再随激励体系演进而改动。

    调用约束（铁律）：必须在业务写操作 `db.commit()` **之后**调用，不得在持有 DB 连接期间
    调用外部服务；实现为纯 DB 操作，内部逐段 try/except，失败不影响主业务流程。
    """

    @staticmethod
    def award(db, uid: str, event: str, extra_exp: int = 0) -> dict:
        """触发一次行为事件：加经验（可能升级并发放升级钻石）+ 评估徽章。

        返回 {"event","exp_gained","level","new_badges"}；event 取 EVENT_* 常量。
        返回值仅供日志/调试，调用方不应据此做业务判断（内部异常被吞，可能只返回部分结果）。
        """
        from app.domains.engagement.services.events import award
        return award(db, uid, event, extra_exp=extra_exp)


class LevelService:
    """等级 / 经验对外入口（新功能 C）。

    - `info`：只读等级详情（等级/经验/称号/特权/距下一级进度/完整阶梯表）；
    - `add_exp`：跨域补加经验（带 FOR UPDATE 行锁，并发安全；跨级时合并发升级钻石）。
    经验累加一律走本服务，**不**提供对外的「直接设置等级」接口（等级必须是经验的派生结果）。
    """

    @staticmethod
    def info(db, uid: str) -> dict:
        """等级详情（含 progress_pct / next_level_exp / ladder）"""
        from app.domains.engagement.services.level import get_level_info
        return get_level_info(db, uid)

    @staticmethod
    def add_exp(db, uid: str, delta: int, reason: str = "") -> dict:
        """累加经验并返回 {old_level,new_level,leveled_up,levels_gained,reward_diamond,...}"""
        from app.domains.engagement.services.level import add_exp
        return add_exp(db, uid, delta, reason=reason)


class MakeupService:
    """补签卡发放对外唯一入口（S4 商品履约）。

    与 `_grant_makeup_card`（打卡场景每次 1 张 + 每日去重）不同：
    `grant` 支持批量 n 张、不受每日去重，专供商品订单履约调用。
    """

    @staticmethod
    def grant(db, uid: str, n: int, reason: str = "purchase") -> int:
        """发放 n 张补签卡，返回发放后的余额。"""
        from app.domains.engagement.routers.tasks.service import grant_makeup_cards
        return grant_makeup_cards(db, uid, n, reason=reason)
