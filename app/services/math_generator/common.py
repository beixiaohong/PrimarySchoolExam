"""数学题生成器公共模块

提供生成器注册表(GENERATORS)与 @register 装饰器，难度映射(DIFFICULTY_MAP)，
作为各年级题型的统一接入与分发入口。
"""
import random
import math
from fractions import Fraction
from typing import List, Optional, Callable, Dict, Tuple

from sqlalchemy.orm import Session

from app.models.problem_type import ProblemType, ProblemCategory
from app.schemas.problem import ProblemItem


GENERATORS: Dict[str, Callable] = {}

def register(code: str):
    """生成器注册装饰器：把被装饰函数挂到全局 GENERATORS[code] 注册表。

    主入口 generate_math_problems 通过 code 查表调用，新增题型只需 @register("code") 即可接入。
    """
    def decorator(func):
        GENERATORS[code] = func
        return func
    return decorator

DIFFICULTY_MAP = {
    "\u57fa\u7840": (1, 2),
    "\u63d0\u9ad8": (3, 4),
    "\u62d4\u9ad8": (4, 5),
    "\u7efc\u5408": (1, 5),
}

__all__ = [
    "DIFFICULTY_MAP",
    "GENERATORS",
    "register",
]
