"""D9 隔离域（IM 与个人账本）对外契约

**本域对其它域不暴露任何能力**：`_EXPORTS` 为空是刻意设计，而非遗漏。

处置依据（文档 02 第三章 D9）：`/api/im` 29 端点 + WebSocket、`/api/ledger` 42 端点，
合计 71 端点（占全站 19%），`im.py` 1,251 行、`ledger.py` 1,086 行，**零测试覆盖**；
维护成本与风险敞口与产出不成比例，故 ① 立即冻结新需求 ② 抽为独立子包
③ 配置开关可整体关闭 ④ 数据已用 `db_im_*` / `db_ledger_*` 前缀隔离，未来独立部署成本极低。

装配关系：只有组合根 `app/main.py` 在 `ENABLE_IM` / `ENABLE_LEDGER`（见 `app/config.py`，
默认开启以保持现状）为真时挂载本域路由；D1–D8 任何代码都不得 `from app.domains.frozen...`
（`.importlinter` 强制）。M1 结束时评估：若与主业无协同，考虑独立为单独产品或下线。
"""
from app.domains._lazy import resolve

_EXPORTS = {}

__all__ = ()


def __getattr__(name):
    return resolve(_EXPORTS, name)


def __dir__():
    return sorted(__all__)
