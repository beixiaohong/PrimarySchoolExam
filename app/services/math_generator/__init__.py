"""
数学题生成器 - 结构变体版
每个题型包含多个结构变体（不同问法/条件组合/情境），非简单换数字。
注册表模式：@register(code) 注册生成器。
"""


from . import common, calc, unit, geo, ratio, app, stat, logic, number, middle, core

from .common import *
from .calc import *
from .unit import *
from .geo import *
from .ratio import *
from .app import *
from .stat import *
from .logic import *
from .number import *
from .middle import *
from .core import *
