"""短信服务（预留接口，暂不实现）

路由层统一调用 send_sms；只有配置了 SMS_PROVIDER 才视为通道启用。
接入具体厂商（阿里云/腾讯云等）时在 send_sms 内补充实现即可。
"""
import logging
import os

logger = logging.getLogger(__name__)


def sms_configured() -> bool:
    """短信通道是否已配置"""
    return bool(os.environ.get("SMS_PROVIDER"))


def send_sms(to_phone: str, code: str) -> bool:
    """发送验证码短信，成功返回 True（当前未接厂商，恒 False）"""
    provider = os.environ.get("SMS_PROVIDER", "")
    if not provider:
        logger.warning("短信通道未配置（SMS_PROVIDER 为空），跳过发送到 %s", to_phone)
        return False
    # TODO: 按 SMS_PROVIDER 对接具体厂商 SDK/API
    logger.warning("短信厂商 %s 尚未实现发送逻辑，跳过发送到 %s", provider, to_phone)
    return False
