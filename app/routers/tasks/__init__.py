"""每日任务 API：3 强制 + 3 可选双轨制

强制任务（每科 1 条，固定不变）：
- 数学：完成 1 套数学练习
- 语文：背诵古诗文（含新背+复习）
- 英语：学单词（含新学+复习）
→ 三科强制全部完成 = 当天全勤，计入卡券进度

可选任务（系统每日从任务池随机生成 3 条）：
→ 全部完成获得 1 张补签卡（可补签中断日）
→ 不可更换，系统自动分配
"""
from fastapi import APIRouter

router = APIRouter()

# 触发各子模块装饰器注册（settings/makeup/daily 共用本包级 router，须在 router 定义之后导入）
from . import settings, makeup, daily, custom, confirm

# 向后兼容：导出顶层常用符号（原 common.py 公共面，供外部 `from app.routers.tasks import ...` 使用）
from .constants import (
    SUBJECTS, MANDATORY_TASKS, MANDATORY_CHOICES, OPTIONAL_POOL,
    CONFIGURABLE_CODES, QUOTA_KEYS, STUDY_FLAG_KEYS,
)
from .service import (
    get_daily_quota, _load_settings, _load_study_flags,
    _build_payload, _get_makeup_balance, _has_makeup_card,
)
from .progress import _today_mastered, _today_new_attempts, _today_challenge_count

# ═══════════════ 自定义任务子路由（custom.py 自带独立 APIRouter） ═══════════════
# 孩子端 /custom（DEPRECATED 保留待复活）与家长端 /custom-task 均在 custom.py，
# 子 router 挂到本 router 下，对外路径仍为 /api/tasks/custom、/api/tasks/custom-task。
router.include_router(custom.router)

# ═══════════════ 完成确认子路由（confirm.py，原独立 task_confirm 模块迁入） ═══════════════
# 刻意不 include 到本 router：对外前缀由 app/main.py 以 /api/task-confirm 挂载，
# 路径与迁移前完全一致（/api/task-confirm/create|list|resolve）。
from .confirm import router as confirm_router  # noqa: E402
