"""古诗文背诵模块 API 路由"""
from fastapi import APIRouter

router = APIRouter()

# 触发各子模块的装饰器注册（必须在 router 定义之后导入）
from . import common, texts, quiz, recite, stats  # noqa: E402,F401

# 重新导出所有原始顶层名称（含下划线私有 helper）
from .common import *  # noqa: E402,F401
from .texts import *  # noqa: E402,F401
from .quiz import *  # noqa: E402,F401
from .recite import *  # noqa: E402,F401
from .stats import *  # noqa: E402,F401
