"""后台登录鉴权依赖（从 app.routers.admin.common 上提至 core，打破 core→routers 循环依赖）。

本模块仅依赖 app.database 与 app.models.admin，不被任何 router 模块反向 import，
故 app.core.permissions 等横切模块可安全引用，避免
app.core.permissions → app.routers.admin.common → app.routers.admin(assets) → app.core.permissions
的导入环。app.routers.admin.common 复用并再导出本模块，存量后台子模块无需改动。
"""
import logging
from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 12


def _require_admin(authorization: str = Header(default=""),
                   db: Session = Depends(get_db)) -> Admin:
    """鉴权依赖：从 Bearer token 解析并校验管理员会话。

    参数：authorization：Authorization 请求头（"Bearer <token>"）。
    业务约束：非 Bearer、token 缺失、登录已失效或过期（12h）、账号已停用均拒绝。
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
    # 账号停用（RBAC 迁移 060 补列 status；历史账号缺列时按 active 处理）
    if getattr(admin, "status", "active") == "disabled":
        raise HTTPException(403, "账号已停用")
    return admin
