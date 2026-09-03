# D9 隔离域（冻结）

IM 与个人账本：冻结新需求，配置开关可整体关闭（ENABLE_IM/ENABLE_LEDGER）。

- 数据归属：db_im_* db_ledger_* 前缀表
- 迁入代码：im.py ledger.py admin/im* admin/ledger* im_crud.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
