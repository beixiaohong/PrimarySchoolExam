# D7 交易与商业化域

商品、订单、支付、订阅、权益发放与核销、对账、钻石账户与计费。

- 数据归属：diamond_accounts diamond_ledger ai_usage_log vip_users；新增 products orders payments 等
- 迁入代码：diamond.py services/diamond.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。
