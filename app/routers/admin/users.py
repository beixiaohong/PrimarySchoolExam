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
from app.domains.family.contracts import _hash_pwd, _validate_pwd

from . import router
from .common import _audit, _require_admin


class AccountReq(BaseModel):
    """账号处理请求：目标用户、操作类型与值。"""
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


@router.get("/users", summary="用户列表（搜索 + 筛选 + 资产 + VIP）")
def list_users(keyword: str = "", grade: int = 0, subject: str = "",
               vip: str = "", active: str = "",
               page: int = 1, page_size: int = 20,
               db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """分页查询用户列表，支持按 user_id/昵称/邮箱/手机号搜索，按 年级/学科/VIP/状态 筛选，
    并附带资产与 VIP 状态。

    参数：keyword：模糊搜索；grade：年级（>0 过滤）；subject：学科；
    vip：''=全部 / 1=仅VIP / 0=非VIP；active：''=全部 / 1=正常 / 0=已停用。
    返回：{"total","page","page_size","items": [...]}。
    副作用：只读。
    """
    q = db.query(User)
    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(User.user_id.like(like), User.nickname.like(like),
                         User.email.like(like), User.phone.like(like)))
    if grade > 0:
        q = q.filter(User.grade == grade)
    if subject:
        q = q.filter(User.subject == subject)
    if active == "1":
        q = q.filter(or_(User.is_active.is_(None), User.is_active == True))  # noqa: E712
    elif active == "0":
        q = q.filter(User.is_active == False)  # noqa: E712
    if vip in ("1", "0"):
        vips_all = {v.user_id for v in db.query(VipUser).all()}
        uids_all = [u.user_id for u in q.all()]
        match = [u for u in uids_all if (u in vips_all) == (vip == "1")]
        q = q.filter(User.user_id.in_(match))
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
            "is_active": getattr(u, "is_active", True) is not False,
        } for u in users],
    }


@router.get("/users/export", summary="导出用户列表（CSV）")
def export_users(keyword: str = "", grade: int = 0, subject: str = "",
                 vip: str = "", active: str = "",
                 db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """按当前筛选条件导出用户列表为 CSV（含资产/VIP/状态）。副作用：只读。"""
    import csv
    import io as _io
    from fastapi.responses import Response

    q = db.query(User)
    kw = keyword.strip()
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(User.user_id.like(like), User.nickname.like(like),
                         User.email.like(like), User.phone.like(like)))
    if grade > 0:
        q = q.filter(User.grade == grade)
    if subject:
        q = q.filter(User.subject == subject)
    if active == "1":
        q = q.filter(or_(User.is_active.is_(None), User.is_active == True))  # noqa: E712
    elif active == "0":
        q = q.filter(User.is_active == False)  # noqa: E712
    users = q.order_by(User.created_at.desc()).limit(5000).all()
    uids = [u.user_id for u in users]
    vips = {v.user_id for v in db.query(VipUser).filter(
        VipUser.user_id.in_(uids)).all()} if uids else set()
    diamonds = dict(db.query(DiamondAccount.user_id, DiamondAccount.balance).filter(
        DiamondAccount.user_id.in_(uids)).all()) if uids else {}
    coins = dict(db.query(CoinLedger.user_id, func.sum(CoinLedger.amount)).filter(
        CoinLedger.user_id.in_(uids)).group_by(CoinLedger.user_id).all()) if uids else {}

    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user_id", "昵称", "年级", "学科", "邮箱", "手机", "钻石", "金币",
                "VIP", "状态", "注册时间", "最近活跃"])
    for u in users:
        w.writerow([
            u.user_id, u.nickname or "", u.grade or "", u.subject or "",
            u.email or "", u.phone or "",
            diamonds.get(u.user_id, 0.0), int(coins.get(u.user_id, 0) or 0),
            "是" if u.user_id in vips else "否",
            "正常" if getattr(u, "is_active", True) is not False else "已停用",
            u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
            u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "",
        ])
    data = "\ufeff" + buf.getvalue()  # BOM 供 Excel 正确识别 UTF-8
    _audit(db, admin, "users:export", "", f"导出用户列表 {len(users)} 条")
    return Response(content=data.encode("utf-8"),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=users.csv"})


@router.get("/users/{user_id}/overview", summary="用户学习概览统计")
def user_overview(user_id: str, db: Session = Depends(get_db),
                  admin: Admin = Depends(_require_admin)):
    """学习概览：做题/试卷/得分/错题/背诵/单词/学习天数/最近活跃。副作用：只读。"""
    from app.models.exam import ExamAttempt, ExamRecord, WrongRecord, Question
    from app.models.classical import ClassicalProgress
    from app.models.vocab import VocabProgress
    from app.models.study_error import StudyError

    u = db.query(User).filter(User.user_id == user_id).first()
    if not u:
        raise HTTPException(404, "用户不存在")

    attempts = db.query(ExamAttempt).filter(ExamAttempt.user_id == user_id).all()
    total_attempts = len(attempts)
    avg_score = round(sum(a.score or 0 for a in attempts) / total_attempts, 1) if total_attempts else 0
    total_questions = sum(a.total or 0 for a in attempts)

    wrong_mastered = db.query(WrongRecord).filter(
        WrongRecord.user_id == user_id, WrongRecord.is_mastered == True).count()  # noqa: E712
    wrong_total = db.query(WrongRecord).filter(WrongRecord.user_id == user_id).count()
    study_errors = db.query(StudyError).filter(StudyError.user_id == user_id).count()

    vocab_learned = db.query(VocabProgress).filter(
        VocabProgress.user_id == user_id,
        VocabProgress.status == "mastered").count()
    vocab_total = db.query(VocabProgress).filter(VocabProgress.user_id == user_id).count()
    classical_learned = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id,
        ClassicalProgress.status == "mastered").count()
    classical_total = db.query(ClassicalProgress).filter(
        ClassicalProgress.user_id == user_id).count()

    last_login = u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else ""
    return {
        "user_id": u.user_id,
        "attempts": total_attempts,
        "total_questions": total_questions,
        "avg_score": avg_score,
        "wrong_total": wrong_total,
        "wrong_mastered": wrong_mastered,
        "study_errors": study_errors,
        "vocab_learned": vocab_learned, "vocab_total": vocab_total,
        "classical_learned": classical_learned, "classical_total": classical_total,
        "last_login": last_login,
        "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
    }


class ActiveReq(BaseModel):
    active: bool  # True=启用 / False=停用


@router.post("/users/{user_id}/active", summary="停用/启用账号")
def toggle_user_active(user_id: str, req: ActiveReq, db: Session = Depends(get_db),
                       admin: Admin = Depends(_require_admin)):
    """停用/启用账号：停用后该账号无法登录、已签发 token 立即失效。
    副作用：更新 is_active、清空 token、记审计日志。"""
    u = db.query(User).filter(User.user_id == user_id.strip()).first()
    if not u:
        raise HTTPException(404, "用户不存在")
    u.is_active = req.active
    if not req.active:
        u.token = None          # 停用即吊销当前登录会话
        u.token_expires_at = None
    db.commit()
    _audit(db, admin, "users:toggle_active", u.user_id,
           f"{'启用' if req.active else '停用'}账号 {u.user_id}")
    return {"ok": True, "active": req.active}


@router.post("/users/account", summary="账号处理（重置密码/改绑解绑邮箱手机/重置为昵称态）")
def handle_account(req: AccountReq, db: Session = Depends(get_db),
                   admin: Admin = Depends(_require_admin)):
    """账号处理：重置登录密码、改绑/解绑邮箱手机、重置为纯昵称态，并记审计日志。

    参数：req：user_id、action(reset_password/set_email/set_phone/reset_nickname)、value。
    业务约束：用户不存在返回 404；邮箱/手机改绑需做排除自身的唯一冲突校验；密码需通过 _validate_pwd。
    副作用：更新 User 并 db.commit、记审计日志。
    返回：{"ok": true, "detail": 操作摘要}。
    """
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
