"""管理后台：登录与会话"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.routers.parent import _hash_pwd, _validate_pwd, _verify_pwd

from . import router
from .common import TOKEN_TTL_HOURS, _require_admin


class LoginReq(BaseModel):
    """管理员登录请求：用户名与密码。"""
    username: str
    password: str


class ChangePwdReq(BaseModel):
    """管理员修改密码请求：原密码与新密码。"""
    old_password: str
    new_password: str


@router.post("/login", summary="管理员登录")
def admin_login(req: LoginReq, db: Session = Depends(get_db)):
    """管理员登录：校验用户名与密码，成功后签发 12h 有效 token 并记录登录时间。

    参数：
        req：username、password。
        db：数据库会话。
    业务约束：用户名或密码错误返回 403。
    副作用：更新 admin.token / token_expires_at / last_login_at 并 db.commit。
    返回：{"token", "username", "role", "expires_at"}。
    """
    admin = db.query(Admin).filter(Admin.username == req.username.strip()).first()
    if not admin or not _verify_pwd(req.password or "", admin.password_hash):
        raise HTTPException(403, "账号或密码不正确")
    admin.token = secrets.token_urlsafe(32)
    admin.token_expires_at = datetime.now() + timedelta(hours=TOKEN_TTL_HOURS)
    admin.last_login_at = datetime.now()
    db.commit()
    return {"token": admin.token, "username": admin.username, "role": admin.role,
            "expires_at": admin.token_expires_at.isoformat(timespec="seconds")}


@router.get("/me", summary="当前管理员信息")
def admin_me(admin: Admin = Depends(_require_admin)):
    """返回当前登录管理员的基本信息（依赖 _require_admin 鉴权）。"""
    return {"username": admin.username, "role": admin.role,
            "last_login_at": admin.last_login_at.isoformat(timespec="seconds")
            if admin.last_login_at else ""}


@router.post("/change-password", summary="修改管理员密码")
def admin_change_pwd(req: ChangePwdReq, db: Session = Depends(get_db),
                     admin: Admin = Depends(_require_admin)):
    """修改当前管理员密码：校验原密码后更新哈希，并使现有 token 失效强制重新登录。

    参数：req：old_password、new_password。
    业务约束：原密码错误返回 403；新密码需通过 _validate_pwd 校验。
    副作用：写入新 password_hash、置 token=None、db.commit（旧 token 失效）。
    返回：{"ok": true}。
    """
    if not _verify_pwd(req.old_password or "", admin.password_hash):
        raise HTTPException(403, "原密码不正确")
    _validate_pwd(req.new_password)
    admin.password_hash = _hash_pwd(req.new_password)
    admin.token = None  # 改密后强制重新登录
    db.commit()
    return {"ok": True}


__all__ = ["LoginReq", "ChangePwdReq", "admin_login", "admin_me", "admin_change_pwd"]
