"""D7 支付网关子包（S4-M2 / 07 §5.2.1 / D6）

本期交付「人工支付网关」抽象：业务层只依赖 `PaymentGateway` 协议，
未来接入微信/支付宝时新增同协议实现并在 `factory.py` 注册、改配置即可，
`order_service` / 后台接口零改动（AC-M0-2-12）。

子包内文件：
- `gateway.py`：PaymentGateway Protocol + 传输结构（PaymentIntent/PaymentStatus/ConfirmPayload/...）；
- `manual_gateway.py`：ManualGateway（本期实现，无任何外部调用，核销以运营操作为准）；
- `factory.py`：get_gateway() 按配置返回网关实例（默认 manual）。
"""
