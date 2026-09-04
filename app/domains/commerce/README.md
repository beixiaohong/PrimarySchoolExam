# D7 交易与商业化域

商品、订单、支付、订阅、权益发放与核销、对账、钻石账户与计费。

- 数据归属：diamond_accounts diamond_ledger ai_usage_log vip_users；新增 products orders payments 等
- 迁入代码：diamond.py services/diamond.py
- 对外接口见 `contracts.py`；禁止其它域直接 import 本域内部模块。

## 履约服务（services/fulfillment.py）

消费 `order.benefit_snapshot` 自动发放权益，成功后 PAID → FULFILLED。

权益分派：
- `diamond` → 同域 `services/diamond.py::grant`
- `vip_days` → `vip_users` 叠加续期（`expire_at = max(now, 现有 expire_at or now) + days`）
- `coupon` + `makeup_card` → 跨域契约 `MakeupService.grant`（D5→D7）

幂等：已 FULFILLED 直接返回；失败保持 PAID（钱已收不关单）。
触发点：核销（confirm-payment）/ 审批通过（approve）后自动调用；补发端点 `POST /api/admin/commerce/orders/{id}/regrant-benefit`。
