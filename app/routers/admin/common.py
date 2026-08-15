"""管理后台共享常量与鉴权/审计辅助（被各子模块复用）"""
import logging

from datetime import datetime
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin, AdminOperationLog

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 12

# 三方配置分组（管理后台展示用；密钥类列表脱敏）
CONFIG_GROUPS = {
    "AI": ["ZHIPU_API_KEY", "AI_MODEL", "AI_BASE_URL",
           "RELAY_API_KEY", "RELAY_BASE_URL", "RELAY_MODEL", "DEEPSEEK_API_KEY"],
    "天气": ["QWEATHER_API_KEY", "QWEATHER_API_HOST", "IPINFO_API_TOKEN"],
    "邮件": ["MAIL_SERVER", "MAIL_PORT", "MAIL_ADDRESS", "MAIL_PASSWORD"],
    "短信（预留）": ["SMS_PROVIDER", "SMS_API_KEY"],
}
SECRET_HINTS = ("KEY", "PASSWORD", "TOKEN")


def _require_admin(authorization: str = Header(default=""),
                   db: Session = Depends(get_db)) -> Admin:
    """鉴权依赖：从 Bearer token 解析并校验管理员会话。

    参数：authorization：Authorization 请求头（"Bearer <token>"）。
    业务约束：非 Bearer、token 缺失、登录已失效或过期（12h）均返回 401。
    返回：已认证的管理员 Admin 对象。
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "未登录")
    admin = db.query(Admin).filter(Admin.token == token).first()
    if not admin:
        raise HTTPException(401, "登录已失效")
    if admin.token_expires_at and admin.token_expires_at < datetime.now():
        raise HTTPException(401, "登录已过期，请重新登录")
    return admin


def _audit(db: Session, admin: Admin, action: str, target: str, detail: str):
    """记录一条管理员操作审计日志并落库。

    参数：
        db：数据库会话。
        admin：当前管理员（取 username）。
        action：操作类型标识（如 "assets:diamond"）。
        target：操作目标（用户 id / 配置键等）。
        detail：操作摘要。
    副作用：新增 AdminOperationLog 并 db.commit。
    """
    db.add(AdminOperationLog(admin=admin.username, action=action,
                             target=target, detail=detail))
    db.commit()


__all__ = [
    "logger", "TOKEN_TTL_HOURS", "CONFIG_GROUPS", "SECRET_HINTS",
    "_require_admin", "_audit",
]
