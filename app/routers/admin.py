"""管理后台 API：管理员登录、用户管理、资产调整、VIP、三方配置、审计日志

- 会话 token 制：登录发 token（12h），Authorization: Bearer <token> 鉴权
- 所有敏感操作落 admin_operation_logs 审计表
- 三方配置读写 system_config 表（优先级高于 .env，60s 缓存，保存后立即失效）
"""
import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.admin import Admin, AdminOperationLog, SystemConfig
from ..models.ai_usage import AIUsageLog
from ..models.diamond import DiamondAccount, DiamondLedger
from ..models.makeup_card import MakeupCard
from ..models.pet import CoinLedger
from ..models.user import User, VipUser
from ..services import sysconfig
from ..services.diamond import grant as grant_diamond
from ..services import review_service
from .parent import _hash_pwd, _validate_pwd, _verify_pwd

logger = logging.getLogger(__name__)

router = APIRouter()

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


# ═══════════════ 请求模型 ═══════════════

class LoginReq(BaseModel):
    username: str
    password: str


class ChangePwdReq(BaseModel):
    old_password: str
    new_password: str


class AccountReq(BaseModel):
    user_id: str
    action: str  # reset_password / set_email / set_phone / reset_nickname
    value: str = ""


class AssetAdjustReq(BaseModel):
    user_id: str
    asset: str  # diamond / coin / makeup
    amount: float
    reason: str


class VipReq(BaseModel):
    user_id: str
    action: str  # add / remove
    note: str = ""


class ConfigSaveReq(BaseModel):
    key: str
    value: str


# ═══════════════ 鉴权 ═══════════════

def _require_admin(authorization: str = Header(default=""),
                   db: Session = Depends(get_db)) -> Admin:
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
    db.add(AdminOperationLog(admin=admin.username, action=action,
                             target=target, detail=detail))
    db.commit()


# ═══════════════ 登录与会话 ═══════════════

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


# ═══════════════ 用户管理 ═══════════════

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


@router.post("/assets/adjust", summary="资产调整（钻石/金币/补签卡，必填理由）")
def adjust_assets(req: AssetAdjustReq, db: Session = Depends(get_db),
                  admin: Admin = Depends(_require_admin)):
    reason = req.reason.strip()
    if not reason:
        raise HTTPException(400, "调整理由必填")
    user = db.query(User).filter(User.user_id == req.user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    uid = user.user_id

    if req.asset == "diamond":
        acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == uid).first()
        if req.amount < 0 and (not acc or acc.balance + req.amount < 0):
            raise HTTPException(400, "扣减后余额不能为负")
        balance = grant_diamond(db, uid, req.amount, reason="admin_adjust")
        detail = f"钻石 {req.amount:+g} → 余额 {balance}"
    elif req.asset == "coin":
        amount = int(req.amount)
        if not amount:
            raise HTTPException(400, "金币数量不能为 0")
        cur = db.query(func.sum(CoinLedger.amount)).filter(
            CoinLedger.user_id == uid).scalar() or 0
        if cur + amount < 0:
            raise HTTPException(400, "扣减后余额不能为负")
        db.add(CoinLedger(user_id=uid, amount=amount, reason=f"管理员调整：{reason}"))
        db.commit()
        detail = f"金币 {amount:+d} → 余额 {cur + amount}"
    elif req.asset == "makeup":
        amount = int(req.amount)
        if not amount:
            raise HTTPException(400, "补签卡数量不能为 0")
        card = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
        if not card:
            card = MakeupCard(user_id=uid, balance=0, total_earned=0, total_used=0)
            db.add(card)
            db.flush()
        if card.balance + amount < 0:
            raise HTTPException(400, "扣减后余额不能为负")
        card.balance += amount
        if amount > 0:
            card.total_earned += amount
        db.commit()
        detail = f"补签卡 {amount:+d} → 余额 {card.balance}"
    else:
        raise HTTPException(400, "资产类型无效（diamond/coin/makeup）")

    _audit(db, admin, "assets:" + req.asset, uid, f"{detail}；理由：{reason}")
    return {"ok": True, "detail": detail}


@router.post("/vip", summary="VIP 设置（增删 + 备注）")
def manage_vip(req: VipReq, db: Session = Depends(get_db),
               admin: Admin = Depends(_require_admin)):
    uid = req.user_id.strip()
    user = db.query(User).filter(User.user_id == uid).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    row = db.query(VipUser).filter(VipUser.user_id == uid).first()

    if req.action == "add":
        if row:
            row.note = req.note.strip()
        else:
            db.add(VipUser(user_id=uid, note=req.note.strip()))
        detail = f"开通 VIP（备注：{req.note.strip() or '无'}）"
    elif req.action == "remove":
        if row:
            db.delete(row)
        detail = "取消 VIP"
    else:
        raise HTTPException(400, "无效操作（add/remove）")

    db.commit()
    _audit(db, admin, "vip:" + req.action, uid, detail)
    return {"ok": True, "detail": detail}


# ═══════════════ 仪表盘 ═══════════════

@router.get("/dashboard", summary="仪表盘（注册趋势/日活/AI 用量/钻石消耗）")
def dashboard(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    today = date.today()
    total_users = db.query(func.count(User.id)).scalar() or 0

    # 注册趋势：近 30 天
    reg_start = datetime.combine(today - timedelta(days=29), datetime.min.time())
    reg_rows = db.query(
        func.date(User.created_at).label("d"), func.count(User.id)
    ).filter(User.created_at >= reg_start).group_by("d").all()
    reg_map = {str(d): c for d, c in reg_rows}
    registration_trend = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": reg_map.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(29, -1, -1)
    ]

    # 日活（近似：last_login_date 在当日的新登录用户数）近 7 天
    dau_map = dict(db.query(User.last_login_date, func.count(User.id)).filter(
        User.last_login_date >= today - timedelta(days=6)
    ).group_by(User.last_login_date).all())
    active_trend = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": dau_map.get(today - timedelta(days=i), 0)}
        for i in range(6, -1, -1)
    ]

    # AI 用量与钻石消耗：近 7 天
    week_start = datetime.combine(today - timedelta(days=6), datetime.min.time())
    ai_usage = db.query(func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= week_start).scalar() or 0
    diamond_spend = db.query(func.sum(DiamondLedger.amount)).filter(
        DiamondLedger.created_at >= week_start, DiamondLedger.amount < 0).scalar() or 0.0
    diamond_grant = db.query(func.sum(DiamondLedger.amount)).filter(
        DiamondLedger.created_at >= week_start, DiamondLedger.amount > 0).scalar() or 0.0

    return {
        "total_users": total_users,
        "vip_count": db.query(func.count(VipUser.user_id)).scalar() or 0,
        "registration_trend": registration_trend,
        "active_trend": active_trend,
        "ai_usage_7d": ai_usage,
        "diamond_spend_7d": round(abs(diamond_spend), 2),
        "diamond_grant_7d": round(diamond_grant, 2),
    }


# ═══════════════ 操作日志 ═══════════════

@router.get("/logs", summary="操作日志")
def list_logs(page: int = 1, page_size: int = 20,
              db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    q = db.query(AdminOperationLog)
    total = q.count()
    rows = q.order_by(AdminOperationLog.id.desc()).offset(
        max(0, (page - 1) * page_size)).limit(page_size).all()
    return {"total": total, "items": [{
        "admin": r.admin, "action": r.action, "target": r.target,
        "detail": r.detail,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
    } for r in rows]}


# ═══════════════ 三方配置 ═══════════════

def _mask(key: str, value: str) -> str:
    """密钥类配置脱敏（仅显示尾 4 位）"""
    if not value:
        return ""
    if any(h in key.upper() for h in SECRET_HINTS):
        return "****" + value[-4:] if len(value) > 4 else "****"
    return value


@router.get("/config", summary="三方配置列表（分组 + 脱敏）")
def list_config(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    rows = {r.key: r for r in db.query(SystemConfig).all()}
    groups = []
    for group, keys in CONFIG_GROUPS.items():
        items = []
        for key in keys:
            row = rows.get(key)
            env_val = sysconfig.get(key, "")  # DB > .env
            items.append({
                "key": key,
                "value": _mask(key, env_val),
                "source": "database" if (row and row.value) else ("env" if env_val else "unset"),
                "updated_by": row.updated_by if row else "",
                "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M") if row and row.updated_at else "",
            })
        groups.append({"group": group, "items": items})
    return {"groups": groups}


@router.post("/config", summary="保存三方配置（写入 system_config，60s 内生效）")
def save_config(req: ConfigSaveReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    key = req.key.strip()
    all_keys = {k for keys in CONFIG_GROUPS.values() for k in keys}
    if key not in all_keys:
        raise HTTPException(400, "配置项不在可管理清单内")
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    old = _mask(key, row.value) if row else ""
    if row:
        row.value, row.updated_by = req.value, admin.username
    else:
        row = SystemConfig(key=key, value=req.value, updated_by=admin.username)
        db.add(row)
    db.commit()
    sysconfig.invalidate(key)  # 保存后立即失效缓存，下次读取即生效
    _audit(db, admin, "config:set", key, f"{old or '（空）'} → {_mask(key, req.value)}")
    return {"ok": True}


# ═══════════════ 多 AI 联合校对（D6）══════════════

class ReviewRunReq(BaseModel):
    content_types: list = []   # 空=全部（middle_question/reading_passage）
    limit: int = 50


class ReviewResolveReq(BaseModel):
    content_type: str         # middle_question / reading_passage
    content_id: int
    verdict: str              # approved / rejected


@router.post("/reviews/run", summary="批量触发多 AI 校对（双供应商独立审阅）")
def reviews_run(req: ReviewRunReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    result = review_service.run_reviews(db, content_types=req.content_types or None,
                                         limit=req.limit, user_id=admin.username)
    _audit(db, admin, "reviews:run", "content_review",
           f"校对 {result['reviewed']} 条（approved={result['approved']}, conflict={result['conflict']}）")
    return {"ok": True, **result}


@router.get("/reviews", summary="审核队列（按状态过滤，默认 conflict）")
def reviews_queue(status: str = "conflict", page: int = 1, page_size: int = 20,
                  db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    data = review_service.list_reviews(db, status=status, page=page, page_size=page_size)
    return data


@router.post("/reviews/resolve", summary="人工裁决（采纳 approved / 驳回 rejected）")
def reviews_resolve(req: ReviewResolveReq, db: Session = Depends(get_db),
                    admin: Admin = Depends(_require_admin)):
    result = review_service.resolve_review(db, req.content_type, req.content_id, req.verdict)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "裁决失败"))
    _audit(db, admin, "reviews:resolve", f"{req.content_type}#{req.content_id}", req.verdict)
    return result
