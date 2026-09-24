"""架构减负（P1）回归闸门：锁住 service→router 越层依赖解耦。

治理总纲 P1-3：ledger_recurring 服务曾 `from app.domains.frozen.routers.ledger
import _adjust_balance` —— service 反向依赖 router 内部函数（越层依赖，router 改动
可能误伤 service，且破坏九域分层）。修复后这两个函数直接来自 service 层
(ledger_calc)，本测试钉死这一点，防止回退。
"""
from app.domains.frozen.services import ledger_recurring
from app.domains.frozen.services import ledger_calc
from app.core.pagination import paginate


def test_ledger_recurring_balance_helpers_resolve_to_service():
    # 函数定义模块必须是 service 层，而非 routers 层（越层依赖的判定依据）
    assert ledger_recurring._adjust_balance.__module__ == \
        "app.domains.frozen.services.ledger_calc"
    assert ledger_recurring._advance_next_run.__module__ == \
        "app.domains.frozen.services.ledger_calc"
    # 与 service 入口是同一对象（语义一致、无副本漂移）
    assert ledger_recurring._adjust_balance is ledger_calc._adjust_balance
    assert ledger_recurring._advance_next_run is ledger_calc._advance_next_run


class _StubQuery:
    """模拟 SQLAlchemy Query：count 返回总数，offset/limit 返回新切片（不原地改）。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def count(self):
        return len(self._rows)

    def order_by(self, *args):
        return self

    def offset(self, o):
        return _StubQuery(self._rows[o:])

    def limit(self, n):
        return _StubQuery(self._rows[:n])

    def all(self):
        return list(self._rows)


def test_paginate_slices_and_counts():
    q = _StubQuery(list(range(25)))
    items, total = paginate(q, page=2, page_size=10)
    assert total == 25
    assert items == list(range(10, 20))  # 第 2 页，10 条


def test_paginate_clamps_page_and_size():
    q = _StubQuery(list(range(25)))
    # page < 1 按 1；page_size 超 200 强制 200（P1-6 上限）
    items, total = paginate(q, page=0, page_size=9999)
    assert total == 25
    assert items == list(range(25))  # 仅 25 条，全部返回
    # page_size = 0 强制 1
    items, _ = paginate(q, page=1, page_size=0)
    assert items == [0]

