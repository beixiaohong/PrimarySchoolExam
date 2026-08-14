"""学习模块错题 + 今日任务汇总路由

错题打通：语法练习、古诗文默写等学习模块答错的题统一记入 study_errors，
与试卷错题（WrongRecord）一起在"错题本"中展示复习。

今日任务：汇总背单词/古诗文/语法/错题四个模块的待办数量，供首页使用。
"""
from fastapi import APIRouter

router = APIRouter()

# 触发各子模块装饰器注册（须在 router 定义之后）
from . import common, errors, dashboard, practice, retry, analysis, review, progress

# 向后兼容：导出全部顶层符号
from .common import *
from .errors import *
from .dashboard import *
from .practice import *
from .retry import *
from .analysis import *
from .review import *
from .progress import *
