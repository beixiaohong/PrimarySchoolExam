"""奖励闭环：家长兑换券 + 孩子心愿单

表（005 迁移已建）：
- reward_coupons：家长创建的兑换券（kind: cartoon/snack/sticker/toy/outing/custom）
- wish_items：孩子心愿单。状态机：
    pending（孩子创建，待家长确认）→ active（确认后进行中）
    → progress 达 target 自动 pending_redeem（待兑现）→ redeemed（家长确认兑现，周报数据源）
  任意非 redeemed 状态可 archive 移除。
"""
from fastapi import APIRouter

router = APIRouter()

# 触发各子模块的装饰器注册（必须在 router 定义之后导入）
from . import common, coupons, wish, exchange, timeline  # noqa: E402,F401

# 重新导出所有原始顶层名称（含下划线私有 helper）
from .common import *  # noqa: E402,F401
from .coupons import *  # noqa: E402,F401
from .wish import *  # noqa: E402,F401
from .exchange import *  # noqa: E402,F401
from .timeline import *  # noqa: E402,F401
