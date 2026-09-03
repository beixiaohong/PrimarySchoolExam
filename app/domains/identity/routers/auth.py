"""用户认证：邮箱验证码注册（字母数字 user_id）、邮箱+密码登录、绑定邮箱、重置密码

规则：
- 登录方式：邮箱 + 密码（昵称登录已关闭，ALLOW_NICKNAME_LOGIN=false）
- 注册：仅邮箱，需邮箱验证码；user_id 由服务端生成随机「字母+数字」串，昵称仅作展示名
- 手机号：暂不开放自注册与绑定（短信通道未配置）；仅保留找回密码的手机入口（实际仍受短信通道限制）
- 验证码 6 位数字，5 分钟有效，校验失败 5 次作废，消费后 used=True
- 频控：同一目标 60 秒内最多 1 条、每天最多 5 条
"""
import hashlib
import logging
import re
import secrets
import string
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import ALLOW_NICKNAME_LOGIN, USER_TOKEN_TTL_HOURS
from app.database import get_db
from app.models.auth import AuthCode
from app.models.user import User
from app.services.mailer import mail_configured, send_email
from app.services.sms import send_sms, sms_configured
from app.routers.parent import _hash_pwd, _validate_pwd, _verify_pwd
from app.domains.identity.routers.user import _auto_upgrade_grade, _streak

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


_USER_ID_ALPHABET = string.ascii_lowercase + string.digits


def _gen_user_id(db: Session) -> str:
    """生成随机「字母+数字」user_id（u 前缀 + 9 位），保证唯一。

    新注册账号不再用昵称/邮箱作 user_id，避免 user_id 与昵称相同。
    """
    for _ in range(12):
        uid = "u" + "".join(secrets.choice(_USER_ID_ALPHABET) for _ in range(9))
        if not db.query(User).filter(User.user_id == uid).first():
            return uid
    raise HTTPException(500, "生成用户ID失败，请稍后重试")


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

    # 关键：落库完成后立即关闭 DB 会话，释放连接，再进行外部阻塞调用
    # （SMTP/SMS 最长可达 90s）。否则连接被 get_db 会话占着直到外部调用结束，
    # 注册/找回密码并发时抽干连接池导致全站卡死（同 267c32c 修复的 AI 接口反模式）。
    # 调用方 send_code 在 _send_code 之后不再使用 db，关闭安全（get_db 的 finally 会幂等再关一次）。
    db.close()

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


def _login_payload(db: Session, user: User, is_new: bool = False) -> dict:
    """登录成功后的统一返回（与 /api/user/login 对齐）

    is_new=True 时登录时间已在创建时写入，跳过同事务 UPDATE
    （代理环境下 INSERT 后立即 UPDATE 同一行不稳定）。
    """
    if not is_new:
        user.last_login_at = datetime.now()
        user.last_login_date = date.today()
        db.commit()
    _auto_upgrade_grade(db)
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "grade": user.grade,
        "subject": user.subject,
        "is_new": is_new,
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


def require_user(authorization: str = Header(default=""),
                 db: Session = Depends(get_db)) -> User:
    """普通用户登录鉴权（Bearer token 会话制，与管理员 _require_admin 一致）。

    返回已登录且未过期的 User；缺失/非法/过期一律 401。
    业务路由统一通过 dependencies=[Depends(require_user)] 强制登录，
    但保留各接口原有的 user_id 参数语义（家长代管孩子场景）。
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "未登录或登录已过期")
    user = db.query(User).filter(User.token == token).first()
    if not user or not user.token:
        raise HTTPException(401, "未登录或登录已过期")
    if user.token_expires_at and user.token_expires_at < datetime.now():
        raise HTTPException(401, "登录已过期，请重新登录")
    if getattr(user, "is_active", True) is False:
        raise HTTPException(401, "账号已停用，请联系管理员")
    return user


async def require_self(authorization: str = Header(default=""),
                       request: Request = None,
                       db: Session = Depends(get_db)) -> User:
    """严格账号绑定：在登录校验基础上，强制请求中的 user_id == 当前登录账号。

    返回登录用户；以下情况分别抛错：
    - 未登录 / token 失效 → 401（同 require_user）
    - 请求携带的 user_id 与登录账号不一致 → 403（禁止用他人 user_id 操作/查他人数据）

    设计要点：家长模式 = 同一账号 + 家长密码解锁，故家长代管孩子不会触发 403（user_id 本就相等）。
    任意登录用户也无法再查/改他人数据（含 /api/diamond/balance、/ledger 等此前仅「需登录」的接口）。
    请求中未携带 user_id（部分只读接口可省略）时不做强制绑定，仍按登录账号处理下游逻辑。
    """
    user = require_user(authorization=authorization, db=db)
    if request is not None:
        # 优先 query；其次 await body 解析 JSON（Starlette 会缓存 body，不影响下游路由解析）
        req_uid = request.query_params.get("user_id") or ""
        if not req_uid:
            try:
                import json
                ct = request.headers.get("content-type", "")
                if "application/json" in ct:
                    raw = await request.body()
                    if raw:
                        data = json.loads(raw)
                        if isinstance(data, dict):
                            req_uid = data.get("user_id") or ""
            except Exception:
                req_uid = ""
        if req_uid and req_uid != user.user_id:
            raise HTTPException(
                403,
                "无权访问该账号的数据（账号绑定校验未通过）",
            )
    return user



# ═══════════════ 接口 ═══════════════

@router.post("/send-code", summary="发送验证码（注册/绑定/重置密码）")
def send_code(req: SendCodeReq, db: Session = Depends(get_db)):
    """发送验证码（注册/绑定/重置密码）。

    请求：{target(邮箱或手机号), purpose=register/bind/reset}；无需家长密码。
    返回：{ok, channel, expires_in(秒)}。
    副作用：频控（同目标 60 秒 1 条、每日 5 条）；落库 auth_codes（6 位、5 分钟有效）；
            调用邮件/短信通道发送（未配置则 503/502）。register/bind 仅支持邮箱（手机号拒绝）；
            reset 仍保留手机入口（实际受短信通道限制）。
    """
    target = (req.target or "").strip().lower() if "@" in (req.target or "") else (req.target or "").strip()
    if req.purpose not in PURPOSES:
        raise HTTPException(400, "验证码用途无效")
    channel = _classify(target)
    # 暂不支持手机号自注册与绑定（短信通道未配置）
    if req.purpose in ("register", "bind") and channel == "phone":
        raise HTTPException(400, "暂不支持手机号注册/绑定，请使用邮箱")
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


@router.post("/register", summary="邮箱注册（验证码 + 密码，user_id 随机字母数字）")
def register(req: RegisterReq, db: Session = Depends(get_db)):
    """邮箱注册（验证码 + 密码，user_id 由服务端生成随机字母数字串）。

    请求：{target(邮箱), code, password, nickname?}；无需家长密码。
    返回：统一登录态 {user_id, grade, subject, is_new, streak_days, created_at}。
    副作用：校验验证码（消费）、校验密码强度；user_id 为随机「字母+数字」串（u 前缀）；
            昵称仅作展示名（缺省取邮箱前缀）；新建用户（默认 6 年级/英语）并落库、
            邮箱标记为已验证。暂不支持手机号注册。
    """
    target = req.target.strip().lower()
    channel = _classify(target)
    if channel == "phone":
        raise HTTPException(400, "暂不支持手机号注册，请使用邮箱")
    if _user_by_target(db, target, channel):
        raise HTTPException(400, "该账号已注册，请直接登录")
    _consume_code(db, "register", target, req.code)
    _validate_pwd(req.password)

    # user_id 由服务端生成随机字母+数字，与昵称彻底解耦
    uid = _gen_user_id(db)
    nickname = (req.nickname or target.split("@")[0]).strip()[:64] or uid
    user = User(
        user_id=uid, nickname=nickname, auth_type="email",
        password_hash=_hash_pwd(req.password),
        grade=6, subject="英语",
        email=target, email_verified=True,
        last_login_at=datetime.now(), last_login_date=date.today(),
    )
    # 注册即签发登录会话 token
    user.token = secrets.token_urlsafe(32)
    user.token_expires_at = datetime.now() + timedelta(hours=USER_TOKEN_TTL_HOURS)
    db.add(user)
    db.commit()
    payload = _login_payload(db, user, is_new=True)
    payload["token"] = user.token
    return payload


@router.post("/login", summary="邮箱+密码登录")
def auth_login(req: LoginReq, db: Session = Depends(get_db)):
    """邮箱 + 密码登录（登录方式已统一为邮箱 + 密码）。

    请求：{account(邮箱), password}；无需家长密码。
    返回：统一登录态（见 _login_payload）。
    副作用：按邮箱定位用户；无密码的账号要求先重置；校验通过后更新 last_login 并自动升级年级。
    """
    account = req.account.strip().lower()
    if not account:
        raise HTTPException(400, "邮箱不能为空")
    if not EMAIL_RE.match(account):
        raise HTTPException(400, "请输入有效的邮箱")
    user = db.query(User).filter(User.email == account).first()
    if not user:
        raise HTTPException(400, "账号不存在")
    if getattr(user, "is_active", True) is False:
        raise HTTPException(403, "账号已停用，请联系管理员")
    if not user.password_hash:
        raise HTTPException(400, "该账号未设置密码，请先重置密码")
    if not _verify_pwd(req.password or "", user.password_hash):
        raise HTTPException(403, "密码不正确")
    # 签发登录会话 token（Bearer 鉴权）
    user.token = secrets.token_urlsafe(32)
    user.token_expires_at = datetime.now() + timedelta(hours=USER_TOKEN_TTL_HOURS)
    payload = _login_payload(db, user)
    payload["token"] = user.token
    return payload


@router.post("/bind", summary="登录后绑定另一通道（邮箱/手机号）")
def bind(req: BindReq, db: Session = Depends(get_db)):
    """登录后绑定另一通道（邮箱/手机号）。

    请求：{user_id, target, code}；无需家长密码（自身账号操作）。
    返回：{ok, channel}。
    副作用：校验验证码（消费）、绑定通道不可被其他账号占用；更新 user.email/phone 并标记已验证。
    """
    user = db.query(User).filter(User.user_id == req.user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    target = req.target.strip().lower()
    channel = _classify(target)
    if channel == "phone":
        raise HTTPException(400, "暂不支持绑定手机号，请使用邮箱")
    if _user_by_target(db, target, channel):
        raise HTTPException(400, "该邮箱已被其他账号绑定")
    _consume_code(db, "bind", target, req.code)
    user.email, user.email_verified = target, True
    db.commit()
    return {"ok": True, "channel": "email"}


@router.post("/reset-password", summary="验证码重置密码")
def reset_password(req: ResetPwdReq, db: Session = Depends(get_db)):
    """验证码重置密码。

    请求：{target, code, new_password}；无需家长密码。
    返回：{ok}。
    副作用：校验验证码（消费）、校验密码强度；重设 password_hash 并落库。
    """
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


@router.get("/me", summary="当前账号认证信息（脱敏，需登录）")
def auth_me(user: User = Depends(require_user)):
    """当前账号认证信息（脱敏，需携带登录 token）。

    依赖：Authorization: Bearer <token>；无需家长密码。
    返回：{user_id, nickname, auth_type, email(脱敏), phone(脱敏), has_password, allow_nickname_login}。
    副作用：只读，无写库。
    """
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "auth_type": user.auth_type,
        "email": _mask_email(user.email) if user.email else None,
        "phone": _mask_phone(user.phone) if user.phone else None,
        "has_password": bool(user.password_hash),
        "allow_nickname_login": ALLOW_NICKNAME_LOGIN,
    }
