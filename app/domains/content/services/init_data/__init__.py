"""
初始化种子数据：题型分类 + 默认词库 + 词组 + 句子 + 语法（古诗文种子见 app/migrations/versions/002_classical_seed.py）
首次启动时自动执行，已有数据则跳过
"""


from . import common, users, problem_types, words, phrases, sentences, grammar, core

from .common import *
from .users import *
from .problem_types import *
from .words import *
from .phrases import *
from .sentences import *
from .grammar import *
from .core import *
