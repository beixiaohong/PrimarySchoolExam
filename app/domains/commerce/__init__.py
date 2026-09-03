"""D7 交易与商业化域（commerce）

职责：商品、订单、支付、订阅、权益发放与核销、对账、钻石账户与计费。

边界纪律（S1-R）：
- 数据归属：diamond_accounts diamond_ledger ai_usage_log vip_users；新增 products orders payments 等
- 迁入代码：diamond.py services/diamond.py
- 其它域只能经本域 contracts.py 定义的接口访问，禁止跨域 import 模型/服务；
- models/schemas 暂留 app/models、app/schemas 共享内核（S1.5 再物理归位），
  表归属以 docs/data-ownership.md 登记为准。
"""
