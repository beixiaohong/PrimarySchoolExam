"""标准分页工具（治理总纲 P1-2 去重 + P1-6 分页上限）。

把 admin 路由里反复手写的 `total = q.count(); rows = q.offset(...).limit(...).all()`
收敛到单一入口，消除同一逻辑四处各写。

设计约束：
- helper 只负责「计数 + 切片」，响应信封由调用方保持既有键名（前端契约不变）。
- page 从 1 开始；page_size 强制 clamp 到 [1, 200]，杜绝无上限全表返回（P1-6）。
- 调用方应在传入前用 .order_by(...) 排好序；Query.count() 内部生成新查询，
  不影响后续切片顺序，可安全先 count 后 offset/limit。
"""
from typing import List, Tuple

from sqlalchemy.orm import Query


def paginate(query: Query, page: int, page_size: int) -> Tuple[List, int]:
    """对 SQLAlchemy Query 做标准分页，返回 (items, total)。

    page 非法（<1）按 1 处理；page_size 强制 [1, 200]。
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 200))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total
