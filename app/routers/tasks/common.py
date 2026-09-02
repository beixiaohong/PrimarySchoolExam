"""每日任务 · 兼容再导出层（DEPRECATED，待显式导入改造后删除）

common.py 已按职责拆分为三个模块：
  - constants.py  学科/强制/可选任务常量、配额、纯查表函数（无 DB）
  - progress.py   各科进度计算（读真实学习数据）
  - service.py    设置读写、任务行生成、payload 构建、全勤连续、补签卡

本文件仅为兼容旧引用 `from .common import *` / `from .common import X` 而保留，
业务代码请直接改从上述三个模块具名导入（见 #272），改造完成后删除本文件。
注意：此处必须显式具名导入（不能用 `from .x import *`），否则下划线开头的
私有名（_UNCONFIGURABLE_CODES / _setting_target 等）不会被带出。
"""
import logging as _logging

from .constants import (  # noqa: F401
    SUBJECTS, MANDATORY_TASKS, MANDATORY_CHOICES, OPTIONAL_POOL,
    _UNCONFIGURABLE_CODES, CONFIGURABLE_CODES, MIN_TARGET, MAX_TARGET,
    CODE_MIN_TARGET, QUOTA_KEYS, TASK_PASS_SCORE, STUDY_FLAG_KEYS,
    _pick_daily_optional, _default_target, _display_title,
    _setting_target, _is_task_enabled, _normalize_mandatory,
    _get_mandatory_codes, _task_def_by_code, _bounded_target,
)
from .progress import (  # noqa: F401
    _today_start, _today_new_attempts, _today_mastered,
    _today_challenge_count, _today_dictation_words, _today_dictation_texts,
    _user_grade, _vocab_all_done, _classical_all_done, _task_progress,
    _available_new_exams, _daily_task_feasible,
)
from .service import (  # noqa: F401
    logger, _load_settings, _load_study_flags, get_daily_quota,
    _ensure_today_rows, _is_full_day, _has_makeup_card, _streak,
    _get_makeup_balance, _grant_makeup_card, _build_payload,
)

logger = _logging.getLogger(__name__)

__all__ = [
    "logger", "SUBJECTS", "MANDATORY_TASKS", "MANDATORY_CHOICES", "OPTIONAL_POOL",
    "_UNCONFIGURABLE_CODES", "CONFIGURABLE_CODES", "MIN_TARGET", "MAX_TARGET",
    "CODE_MIN_TARGET", "QUOTA_KEYS", "TASK_PASS_SCORE",
    "_pick_daily_optional", "_default_target", "_display_title",
    "_load_settings", "_load_study_flags", "_setting_target",
    "_is_task_enabled", "_normalize_mandatory", "_get_mandatory_codes",
    "_task_def_by_code", "_bounded_target", "get_daily_quota",
    "STUDY_FLAG_KEYS", "_today_start", "_today_new_attempts",
    "_today_mastered", "_today_challenge_count", "_today_dictation_words",
    "_today_dictation_texts", "_user_grade", "_vocab_all_done",
    "_classical_all_done", "_task_progress", "_available_new_exams",
    "_daily_task_feasible", "_ensure_today_rows",
    "_is_full_day", "_has_makeup_card", "_streak", "_get_makeup_balance",
    "_grant_makeup_card", "_build_payload",
]
