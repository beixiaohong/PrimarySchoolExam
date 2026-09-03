"""支付网关工厂（S4-M2 / 07 §5.2.1 / D6）

按配置 `PAYMENT_GATEWAY`（默认 manual）返回网关实例。未来接入微信/支付宝：
实现同 `PaymentGateway` 协议，调用 `register_gateway("wechat", WechatPayGateway)`，
并配置 `PAYMENT_GATEWAY=wechat` —— `order_service` / 后台接口零改动（AC-M0-2-12）。

🔴 持连铁律：工厂仅做配置读取与实例构建，无 DB / 外部阻塞调用。
"""
import os

from .gateway import PaymentGateway
from .manual_gateway import ManualGateway

# 已注册网关：name -> 类（不实例化，get_gateway 时构建）
_GATEWAYS = {"manual": ManualGateway}


def register_gateway(name: str, cls) -> None:
    """注册新网关实现（未来 wechat/alipay 在此登记）。"""
    _GATEWAYS[name] = cls


def get_gateway() -> PaymentGateway:
    """返回当前配置的网关实例（未知名称回退 manual，保证不中断主链路）。"""
    name = os.environ.get("PAYMENT_GATEWAY", "manual")
    cls = _GATEWAYS.get(name, ManualGateway)
    return cls()
