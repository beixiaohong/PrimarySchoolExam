"""每日任务 API：强制 + 可选双轨制

强制任务（按学科配置，**家长可整体替换默认项**）：
- 默认三科各 1 条：数学完成 1 套练习 / 语文背诵古诗文（新背 + 复习）/ 英语学单词（新学 + 复习）
- 家长在任务设置里按学科提交完整 code 列表 → **整体替换**该科默认值；
  该科未配置或配置为空时才回退上述默认项（语义自 2b3dd4c 起，非「默认固定 + 追加」）
- 三科强制全部完成 = 当天全勤，计入卡券进度

可选任务（家长可配置列表；未配置时系统每日从任务池随机生成 3 条）：
→ 全部完成获得 1 张补签卡（可补签中断日）

家长自定义任务（task_code 形如 `custom:N`，subject 可为「其他」）：
→ 生命周期由 /custom-task 增删改接口自行管理（更新/删除时同步移除今日未完成行），
  不受任务设置保存的清理逻辑影响（详见 settings.py 保存流程与 2026-09-02 的 KeyError 修复）
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
