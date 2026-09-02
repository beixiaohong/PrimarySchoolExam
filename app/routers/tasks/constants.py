"""每日任务 · 常量与纯查表函数（无 DB 依赖）

从原 common.py 拆分而来：学科/强制/可选任务常量、家长可配置项、以及
不访问数据库的纯函数（任务定义查表、目标数归一化、确定性随机抽取等）。
"""
import hashlib
import re

from fastapi import HTTPException

SUBJECTS = ["数学", "语文", "英语"]

# ═══════════════ 强制任务（每科固定 1 条，不可更换） ═══════════════

MANDATORY_TASKS = {
    "数学": {"code": "math_exam", "title": "完成数学练习", "target": 2, "manual": False,
             "ico": "🧮", "desc": "刷题中心完成数学试卷（套数由家长配置，每套正确率需 ≥70%；须做不同的新卷，重复刷同一张不计入）"},
    "语文": {"code": "chi_classical", "title": "背诵古诗文（新背+复习）", "target": 1, "manual": False,
             "ico": "📜", "desc": "背诵中心完成今日新背内容，并完成当日到期复习额度（或全部到期复习亦可）"},
    "英语": {"code": "eng_vocab", "title": "学单词（新学+复习）", "target": 5, "manual": False,
             "ico": "🔤", "desc": "背单词模块完成今日新学单词，并完成当日到期复习额度（或全部到期复习亦可）"},
}

# ═══════════════ 可选任务池（系统每日随机抽 3 条） ═══════════════

OPTIONAL_POOL = [
    # 数学
    {"code": "math_fix", "title": "订正 10 道数学错题", "target": 10, "manual": False,
     "ico": "📕", "desc": "错题本重做或标记已掌握", "subject": "数学"},
    {"code": "math_teach", "title": "给家长讲 1 道题", "target": 1, "manual": True,
     "ico": "🎓", "desc": "挑一道今天的题讲给家长听", "subject": "数学"},
    {"code": "math_challenge", "title": "数学 60 秒挑战赛 1 次", "target": 1, "manual": False,
     "ico": "⚡", "desc": "限时挑战赛，60 秒内尽可能多答对；本场正确率需 ≥ 80% 才算完成", "subject": "数学"},
    {"code": "math_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成数学同步练习后，找家长确认", "subject": "数学"},
    # 语文
    {"code": "chi_exam", "title": "完成 1 套语文练习", "target": 1, "manual": False,
     "ico": "🖋️", "desc": "刷题中心做一套语文试卷（须做不同的新卷，重复刷同一张不计入）", "subject": "语文"},
    {"code": "chi_read", "title": "朗读课文 5 分钟", "target": 5, "manual": True,
     "ico": "🎙️", "desc": "大声朗读课文或古诗，完成后由家长确认", "subject": "语文"},
    {"code": "chi_dictation", "title": "默写 3 首古诗", "target": 3, "manual": False,
     "ico": "✍️", "desc": "在背诵中心完成古诗文默写", "subject": "语文"},
    {"code": "chi_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成语文同步练习后，找家长确认", "subject": "语文"},
    # 英语
    {"code": "eng_exam", "title": "完成 1 套英语练习", "target": 1, "manual": False,
     "ico": "📝", "desc": "刷题中心做一套英语试卷（须做不同的新卷，重复刷同一张不计入）", "subject": "英语"},
    {"code": "eng_dictation", "title": "听写 10 个单词", "target": 10, "manual": False,
     "ico": "👂", "desc": "在听写磨耳朵完成单词听写", "subject": "英语"},
    {"code": "eng_challenge", "title": "英语 60 秒挑战赛 1 次", "target": 1, "manual": False,
     "ico": "⚡", "desc": "限时挑战赛，60 秒内尽可能多答对；本场正确率需 ≥ 80% 才算完成", "subject": "英语"},
    {"code": "eng_sync", "title": "学习平板完成同步练习", "target": 1, "manual": True,
     "ico": "📱", "desc": "在学习平板完成英语同步练习后，找家长确认", "subject": "英语"},
    # 新增：可配置为强制任务的家庭类手动确认型（家长确认完成）
    {"code": "reading", "title": "完成阅读", "target": 1, "manual": True,
     "ico": "📖", "desc": "完成阅读任务（含朗读/课外阅读），家长确认", "subject": "语文"},
    {"code": "family_homework", "title": "完成家庭作业", "target": 1, "manual": True,
     "ico": "📝", "desc": "完成当日家庭作业，家长确认", "subject": "语文"},
]

# 每科可选的「强制任务类型」库（家长可为每科自定义强制任务，替换默认三科固定项）
MANDATORY_CHOICES = {
    "数学": ["math_exam", "math_sync", "math_fix", "math_teach", "math_challenge"],
    "语文": ["chi_classical", "chi_exam", "chi_read", "chi_dictation", "chi_sync",
             "reading", "family_homework"],
    "英语": ["eng_vocab", "eng_exam", "eng_dictation", "eng_challenge", "eng_sync",
             "reading"],
}

# 家长可配置目标数量的任务（背诵类固定「全量完成」语义，不可配置目标数）
_UNCONFIGURABLE_CODES = {"chi_classical", "eng_vocab"}
CONFIGURABLE_CODES = [t["code"] for t in [
    MANDATORY_TASKS["数学"], MANDATORY_TASKS["语文"], MANDATORY_TASKS["英语"],
]] + [t["code"] for t in OPTIONAL_POOL]
# 去重并排除不可配置项
CONFIGURABLE_CODES = [c for c in dict.fromkeys(CONFIGURABLE_CODES)
                      if c not in _UNCONFIGURABLE_CODES]

MIN_TARGET, MAX_TARGET = 1, 50
# 按任务单独设置的目标下限（默认为空：数值由家长配置，系统只提供能力）
CODE_MIN_TARGET = {}

# 家长可配置的背诵额度（quotas）：{键: (最小值, 最大值, 默认值)}
# 语义为「每轮新学数量」：不限制每日轮数，学完一轮可立即开下一轮
QUOTA_KEYS = {
    "daily_new_words": (1, 100, 20),   # 每轮新学单词数
    "daily_new_texts": (1, 50, 5),     # 每轮新背古诗文数
    "daily_review_words": (1, 100, 10),  # 每天需复习的单词数（到期复习的每日额度，积压可逐日消化）
    "daily_review_texts": (1, 50, 5),   # 每天需复习的古诗文数
}

# 练习类任务的完成门槛（分数≥70才算完成）
TASK_PASS_SCORE = 70

# 学习开关（settings_json 顶层 bool）：预习下学期 / 课堂同步 / 小升初衔接
STUDY_FLAG_KEYS = ("include_next", "sync_mode", "xsc_bridge")


# ═══════════════ 每日可选任务生成（确定性随机） ═══════════════

def _pick_daily_optional(user_id: str, today, settings: dict = None) -> list:
    """基于日期+用户名确定性随机选 3 条可选任务（同一天同一用户结果固定）"""
    seed = f"{user_id}:{today}:{'daily-optional'}"
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    # 过滤掉已禁用的任务
    pool = [t for t in OPTIONAL_POOL if _is_task_enabled(settings or {}, t["code"])]
    if not pool:
        pool = list(OPTIONAL_POOL)  # 全部禁用时回退到全量
    picked = []
    for i in range(3):
        idx = (h >> (i * 8)) % len(pool)
        picked.append(pool.pop(idx))
        if not pool:
            pool = [t for t in OPTIONAL_POOL if _is_task_enabled(settings or {}, t["code"])]
            if not pool:
                pool = list(OPTIONAL_POOL)
    return picked


# ═══════════════ 工具函数 ═══════════════

def _default_target(code: str) -> int:
    for t in list(MANDATORY_TASKS.values()) + OPTIONAL_POOL:
        if t["code"] == code:
            return t["target"]
    return 1


def _display_title(pool_title: str, target: int, default_target: int) -> str:
    if target == default_target:
        return pool_title
    # 替换最后一个数字（避免误改固定数值如"60秒"）
    parts = re.split(r"(\d+)", pool_title)
    # parts 交替 [文本, 数字, 文本, 数字, ...]，从后往前找第一个数字段
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].isdigit():
            parts[i] = str(target)
            break
    return "".join(parts)


# ═══════════════ 家长设置（纯函数部分） ═══════════════

def _normalize_mandatory(raw) -> dict:
    """将存储的 mandatory 归一化为 {subject: [完整 code 列表]}（兼容旧格式单 code 字符串）。

    新语义：列表为该科强制任务的完整集合（可替换默认固定项）；空列表 = 未配置，由
    _get_mandatory_codes 回退到默认任务，保证老用户（历史上存过空数组）不受影响。
    """
    out = {}
    if not isinstance(raw, dict):
        return out
    for subj, val in raw.items():
        if subj not in SUBJECTS:
            continue
        codes = [val] if isinstance(val, str) else (val if isinstance(val, list) else [])
        cleaned = []
        for c in codes:
            if isinstance(c, str) and c and c not in cleaned:
                cleaned.append(c)
        out[subj] = cleaned
    return out


def _get_mandatory_codes(settings: dict, subject: str) -> list:
    """该科强制任务 code 列表：家长配置优先（可自定义科目/类型/数量），
    未配置则回退默认三科固定任务。"""
    cfg = settings.get("mandatory", {}).get(subject, [])
    if cfg:
        valid = [c for c in cfg if c in MANDATORY_CHOICES.get(subject, [])]
        if valid:
            return valid
    return [MANDATORY_TASKS[subject]["code"]]


def _task_def_by_code(code: str) -> dict | None:
    """按 code 查任务定义（含强制任务，补全 subject 字段）"""
    for subj, t in MANDATORY_TASKS.items():
        if t["code"] == code:
            return {**t, "subject": subj}
    for t in OPTIONAL_POOL:
        if t["code"] == code:
            return t
    return None


def _bounded_target(code: str, v: int) -> int:
    """目标数上下限校验：全局 1-50，个别任务可另设下限"""
    lo = max(MIN_TARGET, CODE_MIN_TARGET.get(code, MIN_TARGET))
    if not lo <= v <= MAX_TARGET:
        raise HTTPException(400, f"{code} 的目标数量需在 {lo}-{MAX_TARGET} 之间")
    return v


def _is_task_enabled(settings: dict, code: str) -> bool:
    """检查任务是否启用（默认全部启用）"""
    enabled = settings.get("enabled", {})
    if not enabled:
        return True
    return enabled.get(code, True)


def _setting_target(settings: dict, code: str) -> int | None:
    """取家长配置的目标数；无配置返回 None（由调用方回退默认 target）"""
    targets = settings.get("targets", settings) if isinstance(settings.get("targets"), dict) else settings
    val = targets.get(code)
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None
