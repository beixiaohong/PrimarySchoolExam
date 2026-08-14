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

# 触发各子模块装饰器注册（须在 router 定义之后）
from . import common, settings, makeup, daily

# 向后兼容：导出全部顶层符号
from .common import *
from .settings import *
from .makeup import *
from .daily import *

# ═══════════════ 自定义任务子路由（独立模块 tasks_custom.py） ═══════════════
# 孩子端 /custom 与家长端 /custom-task 相关接口在 tasks_custom 模块，
# 其子 router 挂到本 router 下，路径仍为 /api/tasks/custom、/api/tasks/custom-task 等。
from app.routers.tasks_custom import router as _tasks_custom_router
router.include_router(_tasks_custom_router)
