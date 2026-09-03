"""D9 隔离域（冻结）（frozen）

职责：IM 与个人账本：冻结新需求，配置开关可整体关闭（ENABLE_IM/ENABLE_LEDGER）。

边界纪律（S1-R）：
- 数据归属：db_im_* db_ledger_* 前缀表
- 迁入代码：im.py ledger.py admin/im* admin/ledger* im_crud.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
