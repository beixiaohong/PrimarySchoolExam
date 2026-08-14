"""背单词路由 - 艾宾浩斯记忆曲线"""
from fastapi import APIRouter

router = APIRouter()

# 触发各子模块的装饰器注册（必须在 router 定义之后导入）
from . import common, words, session, stats  # noqa: E402,F401

# 重新导出所有原始顶层名称（含下划线私有 helper）
from .common import *  # noqa: E402,F401
from .words import *  # noqa: E402,F401
from .session import *  # noqa: E402,F401
from .stats import *  # noqa: E402,F401
