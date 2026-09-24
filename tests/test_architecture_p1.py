"""架构减负（P1）回归闸门：锁住 service→router 越层依赖解耦。

治理总纲 P1-3：ledger_recurring 服务曾 `from app.domains.frozen.routers.ledger
import _adjust_balance` —— service 反向依赖 router 内部函数（越层依赖，router 改动
可能误伤 service，且破坏九域分层）。修复后这两个函数直接来自 service 层
(ledger_calc)，本测试钉死这一点，防止回退。
"""
from app.domains.frozen.services import ledger_recurring
from app.domains.frozen.services import ledger_calc


def test_ledger_recurring_balance_helpers_resolve_to_service():
    # 函数定义模块必须是 service 层，而非 routers 层（越层依赖的判定依据）
    assert ledger_recurring._adjust_balance.__module__ == \
        "app.domains.frozen.services.ledger_calc"
    assert ledger_recurring._advance_next_run.__module__ == \
        "app.domains.frozen.services.ledger_calc"
    # 与 service 入口是同一对象（语义一致、无副本漂移）
    assert ledger_recurring._adjust_balance is ledger_calc._adjust_balance
    assert ledger_recurring._advance_next_run is ledger_calc._advance_next_run
