"""成就实时授予服务（新功能 B 成就系统升级，2026Q4）

背景：原实现（`routers/badges.py`）是「访问时全量扫描派生授予」，三个短板：
① 实时性差（不访问不授予，用户解锁了但看不到）；② 每次固定 12 条聚合查询（哪怕只为 1 枚徽章）；
③ 无进度展示（前端只知道「已得/未得」）。
本模块把成就领域逻辑从 router 下沉到服务层，升级为**事件驱动实时授予 + 进度可展示**，
router 退化为薄 HTTP 层。

设计要点
1. **单一真相源 `BADGE_RULES`**：每枚徽章只在一处声明 `metric`（取哪个指标）/ `target`（阈值）/
   `category`（分类）/ `event`（触发事件）。「是否达标」与「进度 current/target/pct」均由它派生，
   杜绝阈值写两处、改一处漏一处 的漂移。
2. **按需计算指标** `_metrics(db, uid, keys)`：`METRIC_FNS` 惰性求值，只要调用方点名的指标。
   事件驱动路径下不再为 1 枚徽章付 12 条聚合查询的代价。
3. **`try_grant(db, uid, event)`**：`event=None` 表示兜底全量评估（`GET /api/badges` 沿用原语义）；
   给定 event 时只评估 `BADGE_RULES[*].event == event` 的徽章。返回本次新解锁的 code 列表供前端 Toast。

铁律合规：纯 DB 读写，**无任何外部/AI 调用**；调用方可在写操作提交后立即调用，
不产生「持 DB 连接等外部阻塞调用」。会话由调用方提供（短会话）。
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

# ── 分类（前端按此分组渲染 tab）──
CATEGORY_STUDY = "study"        # 学习
CATEGORY_PERSIST = "persist"    # 坚持
CATEGORY_SOCIAL = "social"      # 社交与目标
CATEGORY_LABELS = {
    CATEGORY_STUDY: "学习",
    CATEGORY_PERSIST: "坚持",
    CATEGORY_SOCIAL: "社交与目标",
}

# ── 触发事件常量：单一真相源在 services/events.py（行为事件抽象）──
# 此处只做再导出，便于既有调用方与测试维持 `from ...achievement import EVENT_X` 不变。
# 之所以不在此重新定义：事件名同时驱动「经验规则」（C 等级）与「徽章规则」（B 成就），
# 两处各写一份字面量必然漂移（写错的事件名不报错、只是静默不授予）。
from app.domains.engagement.services.events import (  # noqa: F401  (再导出)
    EVENT_CHALLENGE_DONE,
    EVENT_CHECKIN,
    EVENT_CLASSICAL_MASTERED,
    EVENT_EXAM_DONE,
    EVENT_FOCUS_DONE,
    EVENT_GOAL_DONE,
    EVENT_MOOD_DONE,
    EVENT_TASK_DONE,
    EVENT_TEACH_PASSED,
    EVENT_VOCAB_MASTERED,
    EVENT_WRONG_MASTERED,
)

# ── 单一真相源：徽章规则表 ──
# metric 取值必须在 METRIC_FNS 中存在；target 为达标阈值；event 为触发事件。
BADGE_RULES = [
    # 学习
    {"code": "first_exam", "emoji": "🎯", "name": "初出茅庐", "desc": "完成第一次刷题",
     "category": CATEGORY_STUDY, "metric": "attempts", "target": 1, "event": EVENT_EXAM_DONE},
    {"code": "exam_10", "emoji": "💯", "name": "刷题达人", "desc": "累计刷题 10 次",
     "category": CATEGORY_STUDY, "metric": "attempts", "target": 10, "event": EVENT_EXAM_DONE},
    {"code": "exam_50", "emoji": "🚀", "name": "刷题狂魔", "desc": "累计刷题 50 次",
     "category": CATEGORY_STUDY, "metric": "attempts", "target": 50, "event": EVENT_EXAM_DONE},
    {"code": "perfect", "emoji": "🔥", "name": "满分学霸", "desc": "一次考试拿到 100 分",
     "category": CATEGORY_STUDY, "metric": "max_score", "target": 100, "event": EVENT_EXAM_DONE},
    {"code": "wrong_5", "emoji": "📚", "name": "错题克星", "desc": "掌握 5 道错题",
     "category": CATEGORY_STUDY, "metric": "wrong_mastered", "target": 5, "event": EVENT_WRONG_MASTERED},
    {"code": "wrong_20", "emoji": "🏆", "name": "错题终结者", "desc": "掌握 20 道错题",
     "category": CATEGORY_STUDY, "metric": "wrong_mastered", "target": 20, "event": EVENT_WRONG_MASTERED},
    {"code": "vocab_50", "emoji": "📖", "name": "单词之星", "desc": "掌握 50 个单词",
     "category": CATEGORY_STUDY, "metric": "vocab_mastered", "target": 50, "event": EVENT_VOCAB_MASTERED},
    {"code": "classical_10", "emoji": "📜", "name": "诗词达人", "desc": "掌握 10 篇古诗文",
     "category": CATEGORY_STUDY, "metric": "classical_mastered", "target": 10, "event": EVENT_CLASSICAL_MASTERED},
    # 坚持
    {"code": "streak_7", "emoji": "🔥", "name": "一周全勤", "desc": "连续学习 7 天",
     "category": CATEGORY_PERSIST, "metric": "streak", "target": 7, "event": EVENT_TASK_DONE},
    {"code": "streak_30", "emoji": "⭐", "name": "月度坚持", "desc": "连续学习 30 天",
     "category": CATEGORY_PERSIST, "metric": "streak", "target": 30, "event": EVENT_TASK_DONE},
    {"code": "mood_7", "emoji": "💖", "name": "心情晴雨表", "desc": "打卡心情 7 天",
     "category": CATEGORY_PERSIST, "metric": "moods", "target": 7, "event": EVENT_MOOD_DONE},
    {"code": "coin_100", "emoji": "🪙", "name": "小金库", "desc": "累计赚到 100 金币",
     "category": CATEGORY_PERSIST, "metric": "coins_in", "target": 100, "event": EVENT_EXAM_DONE},
    {"code": "tree_300", "emoji": "🌳", "name": "参天大树", "desc": "成长值达到 300",
     "category": CATEGORY_PERSIST, "metric": "tree_score", "target": 300, "event": EVENT_EXAM_DONE},
    # 社交与目标
    {"code": "teach_1", "emoji": "🎓", "name": "小老师出道", "desc": "把一道题给家长讲清楚",
     "category": CATEGORY_SOCIAL, "metric": "teach_passed", "target": 1, "event": EVENT_TEACH_PASSED},
    {"code": "challenge_10", "emoji": "⚡", "name": "挑战先锋", "desc": "参加 10 次挑战赛",
     "category": CATEGORY_SOCIAL, "metric": "challenges", "target": 10, "event": EVENT_CHALLENGE_DONE},
    {"code": "goal_1", "emoji": "🎯", "name": "目标达成者", "desc": "达成第 1 个学习目标",
     "category": CATEGORY_SOCIAL, "metric": "goals_done", "target": 1, "event": EVENT_GOAL_DONE},
    {"code": "goal_3", "emoji": "🏅", "name": "目标达人", "desc": "累计达成 3 个学习目标",
     "category": CATEGORY_SOCIAL, "metric": "goals_done", "target": 3, "event": EVENT_GOAL_DONE},
    {"code": "goal_5", "emoji": "👑", "name": "习惯大师", "desc": "累计达成 5 个学习目标",
     "category": CATEGORY_SOCIAL, "metric": "goals_done", "target": 5, "event": EVENT_GOAL_DONE},
]

# 对外只暴露展示字段（不泄露 metric/target/event 内部实现）
_PUBLIC_KEYS = ("code", "emoji", "name", "desc", "category")


# ══════════════════════════ 指标计算（按需惰性求值） ══════════════════════════

def _m_attempts(db: Session, uid: str) -> int:
    from app.models.exam import ExamAttempt
    return db.query(func.count()).filter(ExamAttempt.user_id == uid).scalar() or 0


def _m_max_score(db: Session, uid: str) -> int:
    from app.models.exam import ExamAttempt
    return db.query(func.max(ExamAttempt.score)).filter(ExamAttempt.user_id == uid).scalar() or 0


def _m_wrong_mastered(db: Session, uid: str) -> int:
    """已掌握错题数 = 试卷错题(WrongRecord) + 学习错题(StudyError)，两处口径合并"""
    from app.models.exam import WrongRecord
    from app.models.study_error import StudyError
    n1 = db.query(func.count()).filter(
        WrongRecord.user_id == uid, WrongRecord.is_mastered == 1).scalar() or 0
    n2 = db.query(func.count()).filter(
        StudyError.user_id == uid, StudyError.is_mastered == 1).scalar() or 0
    return n1 + n2


def _m_streak(db: Session, uid: str) -> int:
    """全勤连续天数：从「任一任务 done」的日期集合向后推算连续。

    注：`DailyTask.task_date` 是 Date 列，读回为 `datetime.date`，
    故必须用 `date` 对象比较（原实现误用 `str(d) in dates`，str 与 date 永不相等
    → 恒返回 0，导致 streak_7 / streak_30 徽章永远无法解锁；此处修正）。
    """
    from app.models.daily_task import DailyTask
    dates = {r[0] for r in db.query(DailyTask.task_date).filter(
        DailyTask.user_id == uid, DailyTask.status == "done").all()}
    d = date.today()
    n = 0
    while d in dates:
        n += 1
        d -= timedelta(days=1)
        if n > 3660:      # 防御性上限（10 年），避免异常数据导致长循环
            break
    return n


def _m_vocab_mastered(db: Session, uid: str) -> int:
    from app.models.vocab import VocabProgress
    return db.query(func.count()).filter(
        VocabProgress.user_id == uid, VocabProgress.status == "mastered").scalar() or 0


def _m_classical_mastered(db: Session, uid: str) -> int:
    from app.models.classical import ClassicalProgress
    return db.query(func.count()).filter(
        ClassicalProgress.user_id == uid, ClassicalProgress.status == "mastered").scalar() or 0


def _m_teach_passed(db: Session, uid: str) -> int:
    from app.models.sprint4 import TeachingRecord
    return db.query(func.count()).filter(
        TeachingRecord.user_id == uid, TeachingRecord.recheck_status == "passed").scalar() or 0


def _m_challenges(db: Session, uid: str) -> int:
    from app.models.sprint4 import ChallengeRecord
    return db.query(func.count()).filter(ChallengeRecord.user_id == uid).scalar() or 0


def _m_moods(db: Session, uid: str) -> int:
    from app.models.mood import MoodCheckin
    return db.query(func.count()).filter(MoodCheckin.user_id == uid).scalar() or 0


def _m_coins_in(db: Session, uid: str) -> int:
    from app.models.pet import CoinLedger
    return db.query(func.coalesce(func.sum(CoinLedger.amount), 0)).filter(
        CoinLedger.user_id == uid, CoinLedger.amount > 0).scalar() or 0


def _m_tree_score(db: Session, uid: str) -> int:
    """成长值（与 tree.py 同口径的简化复制，避免 services→routers 反向依赖）"""
    from app.models.exam import AttemptAnswer, ExamAttempt, WrongRecord
    from app.models.study_error import StudyError
    from app.models.vocab import VocabProgress
    from app.models.classical import ClassicalProgress
    from app.models.daily_task import DailyTask
    from app.models.sprint4 import ChallengeRecord, TeachingRecord
    from app.models.mood import MoodCheckin

    attempts = db.query(func.count(func.distinct(ExamAttempt.id))).filter(
        ExamAttempt.user_id == uid).scalar() or 0
    correct_ans = db.query(func.count()).select_from(AttemptAnswer).join(
        ExamAttempt, ExamAttempt.id == AttemptAnswer.attempt_id).filter(
        AttemptAnswer.is_correct == 1, ExamAttempt.user_id == uid).scalar() or 0
    wrong_m = db.query(func.count()).filter(
        WrongRecord.user_id == uid, WrongRecord.is_mastered == 1).scalar() or 0
    study_m = db.query(func.count()).filter(
        StudyError.user_id == uid, StudyError.is_mastered == 1).scalar() or 0
    vocab_m = db.query(func.count()).filter(
        VocabProgress.user_id == uid, VocabProgress.status == "mastered").scalar() or 0
    cls_m = db.query(func.count()).filter(
        ClassicalProgress.user_id == uid, ClassicalProgress.status == "mastered").scalar() or 0
    tasks_done = db.query(func.count()).filter(
        DailyTask.user_id == uid, DailyTask.status == "done").scalar() or 0
    chal = db.query(func.count(func.distinct(ChallengeRecord.id))).filter(
        ChallengeRecord.user_id == uid).scalar() or 0
    teach_p = db.query(func.count()).filter(
        TeachingRecord.user_id == uid, TeachingRecord.recheck_status == "passed").scalar() or 0
    mood = db.query(func.count(func.distinct(MoodCheckin.id))).filter(
        MoodCheckin.user_id == uid).scalar() or 0
    return (attempts * 2 + correct_ans + (wrong_m + study_m) * 3 + vocab_m
            + cls_m * 2 + tasks_done + chal * 2 + teach_p * 3 + mood)


def _m_goals_done(db: Session, uid: str) -> int:
    """累计达成目标数：学习目标管理台(learning_goals.status=done) + 老学期目标(goal_items.status=done)"""
    from app.models.learning_goal import LearningGoal
    from app.models.reward import GoalItem
    n1 = db.query(func.count()).filter(
        LearningGoal.user_id == uid, LearningGoal.status == "done").scalar() or 0
    n2 = db.query(func.count()).filter(
        GoalItem.user_id == uid, GoalItem.status == "done").scalar() or 0
    return n1 + n2


# 指标名 → 计算函数（惰性求值，仅算调用方点名的指标）
METRIC_FNS = {
    "attempts": _m_attempts,
    "max_score": _m_max_score,
    "wrong_mastered": _m_wrong_mastered,
    "streak": _m_streak,
    "vocab_mastered": _m_vocab_mastered,
    "classical_mastered": _m_classical_mastered,
    "teach_passed": _m_teach_passed,
    "challenges": _m_challenges,
    "moods": _m_moods,
    "coins_in": _m_coins_in,
    "tree_score": _m_tree_score,
    "goals_done": _m_goals_done,
}


def _metrics(db: Session, user_id: str, keys=None) -> dict:
    """按需计算指标。keys=None 表示全量（进度展示需要）。"""
    wanted = list(METRIC_FNS.keys()) if keys is None else [k for k in keys if k in METRIC_FNS]
    return {k: METRIC_FNS[k](db, user_id) for k in wanted}


def _earned_map(db: Session, user_id: str) -> dict:
    """已得徽章：code → 首次达成时间"""
    from app.models.badge import BadgeEarned
    return {b.badge_code: b.earned_at for b in db.query(BadgeEarned).filter(
        BadgeEarned.user_id == user_id).all()}


def _grant_pending(db: Session, user_id: str, pending: list, m: dict) -> list:
    """对「未得且已达标」的徽章落库授予，返回本次新解锁 code 列表（一次性提交）。"""
    from app.models.badge import BadgeEarned
    newly = []
    for r in pending:
        if (m.get(r["metric"], 0) or 0) >= r["target"]:
            db.add(BadgeEarned(user_id=user_id, badge_code=r["code"]))
            newly.append(r["code"])
    if newly:
        db.commit()
    return newly


def progress_of(rule: dict, m: dict) -> dict:
    """单枚徽章的进度：{current, target, pct}（pct 上限 100，供前端进度条）"""
    cur = int(m.get(rule["metric"], 0) or 0)
    target = int(rule["target"])
    pct = 100 if target <= 0 else min(100, int(cur * 100 / target))
    return {"current": cur, "target": target, "pct": pct}


# ══════════════════════════ 对外主入口 ══════════════════════════

def try_grant(db: Session, user_id: str, event: str = None) -> list:
    """事件驱动授予徽章，返回本次新解锁的 code 列表。

    - `event=None`：兜底全量评估（`GET /api/badges` 沿用原语义，保证不漏授予）。
    - 指定 event：只评估 `BADGE_RULES[*].event == event` 的徽章，且只计算这些徽章需要的指标。

    调用方须在写操作 commit 之后调用；本函数纯 DB，无外部调用，失败由调用方 try/except 兜底。
    """
    if not user_id:
        return []
    rules = BADGE_RULES if event is None else [r for r in BADGE_RULES if r["event"] == event]
    if not rules:
        return []  # 未登记的事件：不评估任何徽章（避免误触发全量扫描）
    earned = _earned_map(db, user_id)
    pending = [r for r in rules if r["code"] not in earned]
    if not pending:
        return []  # 全部已得：零查询返回
    m = _metrics(db, user_id, {r["metric"] for r in pending})
    return _grant_pending(db, user_id, pending, m)


def list_badges(db: Session, user_id: str) -> dict:
    """徽章墙全量数据（含进度与分类）。

    副作用：先做一次兜底全量授予（与原 `GET /api/badges` 语义一致），
    保证「历史数据达标但从未访问过徽章墙」的用户也能补齐。
    返回：{total, earned, newly, categories, items[{code,emoji,name,desc,category,earned,earned_at,progress}]}。
    """
    m = _metrics(db, user_id)                       # 进度展示需要全量指标（单次遍历算完）
    earned_map = _earned_map(db, user_id)
    newly = _grant_pending(db, user_id,
                           [r for r in BADGE_RULES if r["code"] not in earned_map], m)
    for code in newly:                              # 补上本次授予，保证下面 earned 判定与落库一致
        earned_map[code] = datetime.now()

    items = []
    for r in BADGE_RULES:
        earned = r["code"] in earned_map
        items.append({
            **{k: r[k] for k in _PUBLIC_KEYS},
            "earned": earned,
            "earned_at": earned_map[r["code"]].strftime("%Y-%m-%d") if earned else None,
            "progress": progress_of(r, m),
        })

    categories = []
    for key, label in CATEGORY_LABELS.items():
        sub = [i for i in items if i["category"] == key]
        categories.append({
            "key": key, "label": label,
            "total": len(sub), "earned": sum(1 for i in sub if i["earned"]),
        })

    return {
        "total": len(items),
        "earned": sum(1 for i in items if i["earned"]),
        "newly": newly,
        "categories": categories,
        "items": items,
    }
