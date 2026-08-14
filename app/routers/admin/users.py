"""管理后台：用户管理（列表 / 账号处理 / 资料编辑）"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin
from app.models.diamond import DiamondAccount
from app.models.makeup_card import MakeupCard
from app.models.pet import CoinLedger
from app.models.user import User, VipUser
from app.routers.parent import _hash_pwd, _validate_pwd

from . import router
from .common import _audit, _require_admin


class AccountReq(BaseModel):
    user_id: str
    action: str  # reset_password / set_email / set_phone / reset_nickname
    value: str = ""


class UserProfileUpdate(BaseModel):
    """修改用户资料：全部可选，传了才改；email/phone 传空串表示解绑。"""
    nickname: Optional[str] = None
    grade: Optional[int] = None
    subject: Optional[str] = None
    city: Optional[str] = None
    email: Optional[str] = None   # 空串 = 解绑
    phone: Optional[str] = None   # 空串 = 解绑


@router.get("/users", summary="用户列表（搜索 + 资产 + VIP）")
def list_users(keyword: str = "", page: int = 1, page_size: int = 20,
               db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(User)
    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(User.user_id.like(like), User.nickname.like(like),
                         User.email.like(like), User.phone.like(like)))
    total = q.count()
    users = q.order_by(User.created_at.desc()).offset(
        max(0, (page - 1) * page_size)).limit(page_size).all()

    uids = [u.user_id for u in users]
    diamonds = {d.user_id: d.balance for d in db.query(DiamondAccount).filter(
        DiamondAccount.user_id.in_(uids)).all()} if uids else {}
    coins = dict(db.query(CoinLedger.user_id, func.sum(CoinLedger.amount)).filter(
        CoinLedger.user_id.in_(uids)).group_by(CoinLedger.user_id).all()) if uids else {}
    makeups = {m.user_id: m.balance for m in db.query(MakeupCard).filter(
        MakeupCard.user_id.in_(uids)).all()} if uids else {}
    vips = {v.user_id for v in db.query(VipUser).filter(
        VipUser.user_id.in_(uids)).all()} if uids else set()

    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "user_id": u.user_id, "nickname": u.nickname, "grade": u.grade,
            "city": u.city,
            "auth_type": u.auth_type, "email": u.email, "phone": u.phone,
            "has_password": bool(u.password_hash),
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
            "last_login_at": u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "",
            "diamonds": diamonds.get(u.user_id, 0.0),
            "coins": int(coins.get(u.user_id, 0) or 0),
            "makeup_cards": makeups.get(u.user_id, 0),
            "is_vip": u.user_id in vips,
        } for u in users],
    }


@router.post("/users/account", summary="账号处理（重置密码/改绑解绑邮箱手机/重置为昵称态）")
def handle_account(req: AccountReq, db: Session = Depends(get_db),
                   admin: Admin = Depends(_require_admin)):
    user = db.query(User).filter(User.user_id == req.user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")

    if req.action == "reset_password":
        _validate_pwd(req.value)
        user.password_hash = _hash_pwd(req.value)
        detail = "重置登录密码"
    elif req.action == "set_email":
        email = req.value.strip().lower()
        if email:
            other = db.query(User).filter(User.email == email,
                                          User.user_id != user.user_id).first()
            if other:
                raise HTTPException(400, f"邮箱已被 {other.user_id} 绑定")
            user.email, user.email_verified = email, True
        else:
            user.email, user.email_verified = None, False
        detail = f"设置邮箱为 {email or '（解绑）'}"
    elif req.action == "set_phone":
        phone = req.value.strip()
        if phone:
            other = db.query(User).filter(User.phone == phone,
                                          User.user_id != user.user_id).first()
            if other:
                raise HTTPException(400, f"手机号已被 {other.user_id} 绑定")
            user.phone, user.phone_verified = phone, True
        else:
            user.phone, user.phone_verified = None, False
        detail = f"设置手机号为 {phone or '（解绑）'}"
    elif req.action == "reset_nickname":
        user.email = user.phone = user.password_hash = None
        user.email_verified = user.phone_verified = False
        user.auth_type, user.nickname = "nickname", user.user_id
        detail = "重置为纯昵称态（清除邮箱/手机/密码）"
    else:
        raise HTTPException(400, "无效操作")

    db.commit()
    _audit(db, admin, "account:" + req.action, user.user_id, detail)
    return {"ok": True, "detail": detail}


@router.put("/users/{user_id}", summary="修改用户资料（昵称/年级/学科/城市/邮箱/手机）")
def update_user_profile(user_id: str, req: UserProfileUpdate,
                        db: Session = Depends(get_db),
                        admin: Admin = Depends(_require_admin)):
    """管理员一次性编辑用户档案字段。全部可选，仅传入的字段被更新。

    - nickname：非空、≤64
    - grade：1-12（与 update_grade 一致）
    - subject/city：strip 后 ≤20/≤50
    - email/phone：空串表示解绑（email_verified/phone_verified 置 False）；
      非空则做「排除自己」的唯一冲突校验，通过后置 verified=True
    返回更新后的档案字段，便于前端直接刷新。副作用：记审计日志。
    """
    user = db.query(User).filter(User.user_id == user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    uid = user.user_id
    changes = []

    if req.nickname is not None:
        nick = req.nickname.strip()
        if not nick:
            raise HTTPException(400, "昵称不能为空")
        if len(nick) > 64:
            raise HTTPException(400, "昵称过长（≤64）")
        if nick != user.nickname:
            user.nickname = nick
            changes.append(f"昵称→{nick}")

    if req.grade is not None:
        if not (1 <= req.grade <= 12):
            raise HTTPException(400, "年级范围无效（1-12）")
        if req.grade != user.grade:
            user.grade = req.grade
            changes.append(f"年级→{req.grade}")

    if req.subject is not None:
        subj = req.subject.strip()
        if len(subj) > 20:
            raise HTTPException(400, "学科过长（≤20）")
        if subj != (user.subject or ""):
            user.subject = subj or None
            changes.append(f"学科→{subj or '（清空）'}")

    if req.city is not None:
        c = req.city.strip()
        if len(c) > 50:
            raise HTTPException(400, "城市过长（≤50）")
        if c != (user.city or ""):
            user.city = c or None
            changes.append(f"城市→{c or '（清空）'}")

    if req.email is not None:
        email = req.email.strip().lower()
        if email:
            if email != (user.email or ""):
                other = db.query(User).filter(
                    User.email == email, User.user_id != uid).first()
                if other:
                    raise HTTPException(400, f"邮箱已被 {other.user_id} 绑定")
                user.email, user.email_verified = email, True
                changes.append(f"邮箱→{email}")
        elif user.email:
            user.email, user.email_verified = None, False
            changes.append("邮箱→（解绑）")

    if req.phone is not None:
        phone = req.phone.strip()
        if phone:
            if phone != (user.phone or ""):
                other = db.query(User).filter(
                    User.phone == phone, User.user_id != uid).first()
                if other:
                    raise HTTPException(400, f"手机号已被 {other.user_id} 绑定")
                user.phone, user.phone_verified = phone, True
                changes.append(f"手机→{phone}")
        elif user.phone:
            user.phone, user.phone_verified = None, False
            changes.append("手机→（解绑）")

    if not changes:
        return {"ok": True, "changed": False, "detail": "无变更"}
    db.commit()
    _audit(db, admin, "profile:update", uid, "；".join(changes))
    return {
        "ok": True, "changed": True, "detail": "；".join(changes),
        "user": {
            "user_id": user.user_id, "nickname": user.nickname,
            "grade": user.grade, "subject": user.subject, "city": user.city,
            "email": user.email, "phone": user.phone,
            "email_verified": user.email_verified,
            "phone_verified": user.phone_verified,
        },
    }


__all__ = ["AccountReq", "UserProfileUpdate", "list_users", "handle_account", "update_user_profile"]
