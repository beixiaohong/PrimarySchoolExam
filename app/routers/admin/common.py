"""管理后台共享常量与鉴权/审计辅助（被各子模块复用）"""
import logging

from datetime import datetime
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin, AdminOperationLog

logger = logging.getLogger(__name__)

# 后台登录鉴权依赖上提至 app.core.auth（打破 core→routers 循环依赖），此处复用并再导出
from app.core.auth import TOKEN_TTL_HOURS, _require_admin

# 三方配置分组（管理后台展示用；密钥类列表脱敏）
CONFIG_GROUPS = {
    "AI": ["ZHIPU_API_KEY", "AI_MODEL", "AI_BASE_URL",
           "RELAY_API_KEY", "RELAY_BASE_URL", "RELAY_MODEL", "DEEPSEEK_API_KEY"],
    "天气": ["QWEATHER_API_KEY", "QWEATHER_API_HOST", "IPINFO_API_TOKEN"],
    "邮件": ["MAIL_SERVER", "MAIL_PORT", "MAIL_ADDRESS", "MAIL_PASSWORD"],
    "短信（预留）": ["SMS_PROVIDER", "SMS_API_KEY"],
}
SECRET_HINTS = ("KEY", "PASSWORD", "TOKEN")


def _audit(db: Session, admin: Admin, action: str, target: str, detail: str,
           *, ip: str = "", user_agent: str = "", amount_fen: int | None = None,
           target_type: str = "", extra_json: str = ""):
    """记录一条管理员操作审计日志并落库（S1-B7 审计增强字段）。

    参数：
        db：数据库会话。
        admin：当前管理员（取 username）。
        action：操作类型标识（如 "assets:diamond"）。
        target：操作目标（用户 id / 配置键等）。
        detail：操作摘要。
        ip：操作来源 IP（建议由请求 request.client.host 传入）。
        user_agent：操作来源 UA。
        amount_fen：涉及金额（分），无则 None。
        target_type：操作对象类型（user/config/asset/vip/order/permission...）。
        extra_json：扩展上下文 JSON 字符串。
    副作用：新增 AdminOperationLog 并 db.commit。
    """
    db.add(AdminOperationLog(
        admin=admin.username, action=action, target=target, detail=detail,
        ip=ip, user_agent=user_agent, amount_fen=amount_fen,
        target_type=target_type, extra_json=extra_json))
    db.commit()


__all__ = [
    "logger", "TOKEN_TTL_HOURS", "CONFIG_GROUPS", "SECRET_HINTS",
    "_require_admin", "_audit",
]
