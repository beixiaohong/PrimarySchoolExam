"""管理后台：登录与会话"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.routers.parent import _hash_pwd, _validate_pwd, _verify_pwd

from . import router
from .common import TOKEN_TTL_HOURS, _require_admin


class LoginReq(BaseModel):
    username: str
    password: str


class ChangePwdReq(BaseModel):
    old_password: str
    new_password: str


@router.post("/login", summary="管理员登录")
def admin_login(req: LoginReq, db: Session = Depends(get_db)):
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
    return {"username": admin.username, "role": admin.role,
            "last_login_at": admin.last_login_at.isoformat(timespec="seconds")
            if admin.last_login_at else ""}


@router.post("/change-password", summary="修改管理员密码")
def admin_change_pwd(req: ChangePwdReq, db: Session = Depends(get_db),
                     admin: Admin = Depends(_require_admin)):
    if not _verify_pwd(req.old_password or "", admin.password_hash):
        raise HTTPException(403, "原密码不正确")
    _validate_pwd(req.new_password)
    admin.password_hash = _hash_pwd(req.new_password)
    admin.token = None  # 改密后强制重新登录
    db.commit()
    return {"ok": True}


__all__ = ["LoginReq", "ChangePwdReq", "admin_login", "admin_me", "admin_change_pwd"]
