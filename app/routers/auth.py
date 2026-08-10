"""用户认证：邮箱/手机号验证码注册、密码登录、绑定、重置密码

规则：
- 验证码 6 位数字，5 分钟有效，校验失败 5 次作废，消费后 used=True
- 频控：同一目标 60 秒内最多 1 条、每天最多 5 条
- 短信通道预留未实现（SMS_PROVIDER 未配置时拒绝手机验证码）
- 昵称快捷登录受 ALLOW_NICKNAME_LOGIN 开关控制（存量账号兼容）
"""
import hashlib
import logging
import re
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import ALLOW_NICKNAME_LOGIN
from ..database import get_db
from ..models.auth import AuthCode
from ..models.user import User
from ..services.mailer import mail_configured, send_email
from ..services.sms import send_sms, sms_configured
from .parent import _hash_pwd, _validate_pwd, _verify_pwd
from .user import _auto_upgrade_grade, _streak

logger = logging.getLogger(__name__)

router = APIRouter()

PURPOSES = ("register", "bind", "reset")
CODE_TTL_SEC = 300          # 验证码有效期 5 分钟
CODE_MAX_FAIL = 5           # 连续校验失败 5 次作废
SEND_INTERVAL_SEC = 60      # 同一目标发送间隔
SEND_DAILY_LIMIT = 5        # 同一目标每日上限
PWD_RESET_SUBJECT = "重置密码验证码"

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
PHONE_RE = re.compile(r"^1\d{10}$")


# ═══════════════ 请求模型 ═══════════════

class SendCodeReq(BaseModel):
    target: str
    purpose: str


class RegisterReq(BaseModel):
    target: str
    code: str
    password: str
    nickname: str = None


class LoginReq(BaseModel):
    account: str
    password: str


class BindReq(BaseModel):
    user_id: str
    target: str
    code: str


class ResetPwdReq(BaseModel):
    target: str
    code: str
    new_password: str


# ═══════════════ 工具函数 ═══════════════

def _classify(target: str) -> str:
    """识别目标类型：email / phone，非法抛 400"""
    if EMAIL_RE.match(target):
        return "email"
    if PHONE_RE.match(target):
        return "phone"
    raise HTTPException(400, "请输入有效的邮箱或 11 位手机号")


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _user_by_target(db: Session, target: str, channel: str):
    if channel == "email":
        return db.query(User).filter(User.email == target).first()
    return db.query(User).filter(User.phone == target).first()


def _send_code(db: Session, purpose: str, target: str) -> None:
    """频控 + 落库 + 发送，失败抛 HTTPException"""
    channel = _classify(target)
    now = datetime.now()

    recent = db.query(AuthCode).filter(
        AuthCode.target == target,
        AuthCode.created_at >= now - timedelta(seconds=SEND_INTERVAL_SEC),
    ).count()
    if recent:
        raise HTTPException(429, "发送太频繁，请 1 分钟后再试")
    day_start = datetime.combine(date.today(), datetime.min.time())
    daily = db.query(AuthCode).filter(
        AuthCode.target == target, AuthCode.created_at >= day_start).count()
    if daily >= SEND_DAILY_LIMIT:
        raise HTTPException(429, "今日验证码次数已用完，请明天再试")

    code = "".join(secrets.choice("0123456789") for _ in range(6))
    db.add(AuthCode(
        purpose=purpose, target=target, code_hash=_code_hash(code),
        expires_at=now + timedelta(seconds=CODE_TTL_SEC),
    ))
    db.commit()

    if channel == "email":
        if not mail_configured():
            raise HTTPException(503, "邮件通道未配置，请联系管理员")
        subject = PWD_RESET_SUBJECT if purpose == "reset" else "验证码"
        if not send_email(target, code, subject=subject):
            raise HTTPException(502, "验证码发送失败，请稍后再试")
    else:
        if not sms_configured():
            raise HTTPException(503, "短信通道暂未开通，请使用邮箱")
        if not send_sms(target, code):
            raise HTTPException(502, "验证码发送失败，请稍后再试")


def _consume_code(db: Session, purpose: str, target: str, code: str) -> None:
    """校验并消费验证码，错误时累计失败次数，达上限作废"""
    row = db.query(AuthCode).filter(
        AuthCode.purpose == purpose, AuthCode.target == target,
        AuthCode.used.is_(False),
    ).order_by(AuthCode.id.desc()).first()
    if not row:
        raise HTTPException(400, "请先获取验证码")
    if row.expires_at < datetime.now():
        raise HTTPException(400, "验证码已过期，请重新获取")
    if row.code_hash != _code_hash(code or ""):
        row.fail_count += 1
        if row.fail_count >= CODE_MAX_FAIL:
            row.used = True  # 错误次数过多作废
        db.commit()
        raise HTTPException(400, "验证码不正确")
    row.used = True
    db.commit()


def _login_payload(db: Session, user: User) -> dict:
    """登录成功后的统一返回（与 /api/user/login 对齐）"""
    user.last_login_at = datetime.now()
    user.last_login_date = date.today()
    db.commit()
    _auto_upgrade_grade(db)
    return {
        "user_id": user.user_id,
        "grade": user.grade,
        "subject": user.subject,
        "is_new": False,
        "streak_days": _streak(db, user.user_id),
        "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else "",
        "message": "欢迎回来！",
    }


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    keep = name[:2] if len(name) > 2 else name[:1]
    return f"{keep}***@{domain}"


def _mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[7:]}"


# ═══════════════ 接口 ═══════════════

@router.post("/send-code", summary="发送验证码（注册/绑定/重置密码）")
def send_code(req: SendCodeReq, db: Session = Depends(get_db)):
    target = (req.target or "").strip().lower() if "@" in (req.target or "") else (req.target or "").strip()
    if req.purpose not in PURPOSES:
        raise HTTPException(400, "验证码用途无效")
    channel = _classify(target)
    bound = _user_by_target(db, target, channel)
    if req.purpose == "register" and bound:
        raise HTTPException(400, "该账号已注册，请直接登录")
    if req.purpose in ("bind", "reset"):
        if req.purpose == "reset" and not bound:
            raise HTTPException(400, "该邮箱/手机号未注册")
        if req.purpose == "bind" and bound:
            raise HTTPException(400, "该邮箱/手机号已被其他账号绑定")
    _send_code(db, req.purpose, target)
    return {"ok": True, "channel": channel, "expires_in": CODE_TTL_SEC}


@router.post("/register", summary="邮箱/手机号注册（验证码 + 密码）")
def register(req: RegisterReq, db: Session = Depends(get_db)):
    target = req.target.strip()
    channel = _classify(target)
    if _user_by_target(db, target, channel):
        raise HTTPException(400, "该账号已注册，请直接登录")
    _consume_code(db, "register", target, req.code)
    _validate_pwd(req.password)

    # user_id 取昵称或目标账号，冲突时追加数字后缀
    nickname = (req.nickname or "").strip()
    base = nickname or (target if channel == "phone" else target.split("@")[0])
    uid, n = base[:64], 0
    while db.query(User).filter(User.user_id == uid).first():
        n += 1
        uid = f"{base[:58]}{n}"
    user = User(
        user_id=uid, nickname=nickname or uid, auth_type=channel,
        password_hash=_hash_pwd(req.password),
        grade=6, subject="英语",
        last_login_date=date.today(),
    )
    if channel == "email":
        user.email, user.email_verified = target, True
    else:
        user.phone, user.phone_verified = target, True
    db.add(user)
    db.commit()
    return _login_payload(db, user)


@router.post("/login", summary="账号密码登录（邮箱/手机号/昵称）")
def auth_login(req: LoginReq, db: Session = Depends(get_db)):
    account = req.account.strip()
    if not account:
        raise HTTPException(400, "账号不能为空")
    if EMAIL_RE.match(account):
        user = db.query(User).filter(User.email == account).first()
    elif PHONE_RE.match(account):
        user = db.query(User).filter(User.phone == account).first()
    else:
        if not ALLOW_NICKNAME_LOGIN:
            raise HTTPException(403, "昵称登录已关闭，请使用邮箱/手机号账号")
        user = db.query(User).filter(
            or_(User.user_id == account, User.nickname == account)).first()
    if not user:
        raise HTTPException(400, "账号不存在")
    if not user.password_hash:
        raise HTTPException(400, "该账号未设置密码，请先重置密码")
    if not _verify_pwd(req.password or "", user.password_hash):
        raise HTTPException(403, "密码不正确")
    return _login_payload(db, user)


@router.post("/bind", summary="登录后绑定另一通道（邮箱/手机号）")
def bind(req: BindReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    target = req.target.strip()
    channel = _classify(target)
    if _user_by_target(db, target, channel):
        raise HTTPException(400, "该邮箱/手机号已被其他账号绑定")
    _consume_code(db, "bind", target, req.code)
    if channel == "email":
        user.email, user.email_verified = target, True
    else:
        user.phone, user.phone_verified = target, True
    db.commit()
    return {"ok": True, "channel": channel}


@router.post("/reset-password", summary="验证码重置密码")
def reset_password(req: ResetPwdReq, db: Session = Depends(get_db)):
    target = req.target.strip()
    channel = _classify(target)
    user = _user_by_target(db, target, channel)
    if not user:
        raise HTTPException(400, "该邮箱/手机号未注册")
    _consume_code(db, "reset", target, req.code)
    _validate_pwd(req.new_password)
    user.password_hash = _hash_pwd(req.new_password)
    db.commit()
    return {"ok": True}


@router.get("/me", summary="当前账号认证信息（脱敏）")
def auth_me(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "auth_type": user.auth_type,
        "email": _mask_email(user.email) if user.email else None,
        "phone": _mask_phone(user.phone) if user.phone else None,
        "has_password": bool(user.password_hash),
        "allow_nickname_login": ALLOW_NICKNAME_LOGIN,
    }
