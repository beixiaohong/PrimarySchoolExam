"""试卷生成 API 路由

功能：
  - 生成九科试卷（Word下载），题目自动入库（试卷不绑定用户）
    小学三科：数学/英语/语文；初中新增六科：物理/化学/生物/道德与法治/历史/地理
  - 查看试卷记录、试卷题目
  - 标记/取消错题（按用户）、标记已掌握
  - 错题列表查询（按用户）
  - 错题专项练习（按用户，生成Word）

设计原则：
  试卷和题目是公共资源（一份卷可给多人用），
  错题记录绑定用户（每人有独立错题本）。
"""
from fastapi import APIRouter

router = APIRouter()

# 触发各子模块装饰器注册（须在 router 定义之后）
from . import common, generate, records, wrong, attempts, collection

# 向后兼容：导出全部顶层符号
from .common import *
from .generate import *
from .records import *
from .wrong import *
from .attempts import *
from .collection import *
