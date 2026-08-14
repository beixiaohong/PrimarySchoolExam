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
from ..models.ai_usage import AIUsageLog, AiQa, WeeklyReport
from ..models.diamond import DiamondAccount, DiamondLedger
from ..models.exam import ExamAttempt, WrongRecord
from ..models.classical import ClassicalDailyLog
from ..models.vocab import VocabDailyLog
from ..models.sprint4 import ChallengeRecord
from ..models.makeup_card import MakeupCard, MakeupUsageLog
from ..models.parent import ParentMessage
from ..models.pet import CoinLedger
from ..models.reward import RewardCoupon
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


class UserProfileUpdate(BaseModel):
    """修改用户资料：全部可选，传了才改；email/phone 传空串表示解绑。"""
    nickname: Optional[str] = None
    grade: Optional[int] = None
    subject: Optional[str] = None
    city: Optional[str] = None
    email: Optional[str] = None   # 空串 = 解绑
    phone: Optional[str] = None   # 空串 = 解绑


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


# ═══════════════ 用户学习记录 ═══════════════
# 行为 → 表映射（核心表聚合；听写/搜题当前无逐用户日志表，前端会标注「未记录」）
#   做题   → exam_attempts
#   错题   → wrong_records
#   背诵   → classical_daily_log
#   背单词 → vocab_daily_log
#   刷题   → challenge_records
#   AI对话 → ai_qa（qa 问答 / explain 讲解）
#   家长记录 → parent_messages（家长留言）/ weekly_reports（成长周报）/ makeup_usage_log（补签，家长确认）

STUDY_CATS = {
    "exam": "做题", "wrong": "错题", "classical": "背诵", "vocab": "背单词",
    "challenge": "刷题", "ai": "AI对话", "parent": "家长记录",
}


@router.get("/users/{user_id}/study-records",
            summary="查询用户学习记录（做题/错题/背诵/背单词/刷题/AI对话/家长记录）")
def user_study_records(user_id: str, category: str = "all", page: int = 1, page_size: int = 30,
                       db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    uid = user_id.strip()
    if not db.query(User).filter(User.user_id == uid).first():
        raise HTTPException(404, "用户不存在")
    want = lambda c: category in ("all", c)

    events = []
    if want("exam"):
        for r in db.query(ExamAttempt).filter(ExamAttempt.user_id == uid).all():
            events.append({
                "time": r.created_at, "category": "exam", "category_name": "做题",
                "summary": f"完成试卷（得分 {r.score}/100，答对 {r.correct}/{r.total}，用时 {r.duration_sec}s）",
                "detail": f"exam_id={r.exam_id}",
            })
    if want("wrong"):
        for r in db.query(WrongRecord).filter(WrongRecord.user_id == uid).all():
            events.append({
                "time": r.wrong_at, "category": "wrong", "category_name": "错题",
                "summary": f"标记错题（题目 #{r.question_id}）{'· 已掌握' if r.is_mastered else ''}",
                "detail": f"练习 {r.practice_count} 次；错因：{r.cause or '未填'}",
            })
    if want("classical"):
        for r in db.query(ClassicalDailyLog).filter(ClassicalDailyLog.user_id == uid).all():
            d = r.learn_date
            events.append({
                "time": datetime.combine(d, datetime.min.time()), "category": "classical",
                "category_name": "背诵",
                "summary": f"古诗文学习（新学 {r.texts_learned} · 复习 {r.texts_reviewed} · 对 {r.correct_count}/错 {r.wrong_count}）",
                "detail": f"日期 {d}",
            })
    if want("vocab"):
        for r in db.query(VocabDailyLog).filter(VocabDailyLog.user_id == uid).all():
            d = r.learn_date
            events.append({
                "time": datetime.combine(d, datetime.min.time()), "category": "vocab",
                "category_name": "背单词",
                "summary": f"背单词（新学 {r.new_words_learned} · 复习 {r.words_reviewed} · 对 {r.correct_count}/错 {r.wrong_count}）",
                "detail": f"日期 {d}",
            })
    if want("challenge"):
        for r in db.query(ChallengeRecord).filter(ChallengeRecord.user_id == uid).all():
            kind_cn = "口算" if r.kind == "math" else ("单词速答" if r.kind == "word" else r.kind)
            events.append({
                "time": r.created_at, "category": "challenge", "category_name": "刷题",
                "summary": f"限时挑战赛（{kind_cn}）：答对 {r.correct}/{r.total}",
                "detail": f"challenge_id={r.id}",
            })
    if want("ai"):
        for r in db.query(AiQa).filter(AiQa.user_id == uid).all():
            qtype = "讲解" if r.q_type == "explain" else "问答"
            events.append({
                "time": r.created_at, "category": "ai", "category_name": "AI对话",
                "summary": f"AI{qtype}：{(r.question or '')[:60]}{'…' if r.question and len(r.question) > 60 else ''}",
                "detail": f"供应商 {r.provider or '-'}",
            })
    if want("parent"):
        for r in db.query(ParentMessage).filter(ParentMessage.user_id == uid).all():
            events.append({
                "time": r.created_at, "category": "parent", "category_name": "家长记录",
                "summary": f"家长留言：{(r.content or '')[:60]}",
                "detail": f"{'已读' if r.read_at else '未读'}" + (f" · {r.created_at.strftime('%Y-%m-%d %H:%M')}" if r.created_at else ""),
            })
        for r in db.query(WeeklyReport).filter(WeeklyReport.user_id == uid).all():
            events.append({
                "time": r.created_at, "category": "parent", "category_name": "家长记录",
                "summary": f"成长周报（{r.week_start}）状态：{r.status}",
                "detail": f"家长寄语：{r.parent_note or '（无）'}",
            })
        for r in db.query(MakeupUsageLog).filter(MakeupUsageLog.user_id == uid).all():
            events.append({
                "time": r.used_at, "category": "parent", "category_name": "家长记录",
                "summary": f"补签卡使用（目标日 {r.target_date}）状态：{r.status}",
                "detail": f"关联任务 task_id={r.task_id}",
            })

    events.sort(key=lambda e: e["time"] or datetime.min, reverse=True)
    counts = {c: sum(1 for e in events if e["category"] == c) for c in STUDY_CATS}
    total = len(events)
    start = max(0, (page - 1) * page_size)
    items = events[start:start + page_size]
    # 时间格式化
    for e in items:
        e["time"] = e["time"].strftime("%Y-%m-%d %H:%M") if e["time"] else ""
    return {"total": total, "page": page, "page_size": page_size,
            "counts": counts, "items": items}


# ═══════════════ 用户资产流水 ═══════════════
# 金币：coin_ledger（余额=SUM(amount)，逐笔无余额快照，后端累计推算）
# 钻石：diamond_ledger（含 balance_after 快照）
# 补签卡：makeup_usage_log（每次使用 -1）
# 卡券：reward_coupons（无逐笔时间戳，按持有量展示 granted/redeemed）

LEDGER_KINDS = {"coin": "金币", "diamond": "钻石", "makeup": "补签卡", "coupon": "卡券"}


@router.get("/users/{user_id}/ledger",
            summary="用户资产流水（金币/钻石/补签卡/卡券）")
def user_ledger(user_id: str, kind: str = "all", page: int = 1, page_size: int = 30,
                db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    uid = user_id.strip()
    if not db.query(User).filter(User.user_id == uid).first():
        raise HTTPException(404, "用户不存在")
    want = lambda k: kind in ("all", k)
    rows = []

    if want("coin"):
        running = 0
        for r in db.query(CoinLedger).filter(CoinLedger.user_id == uid).order_by(
                CoinLedger.created_at, CoinLedger.id).all():
            running += r.amount
            rows.append({"time": r.created_at, "kind": "coin", "kind_name": "金币",
                         "amount": r.amount, "balance_after": running, "reason": r.reason,
                         "ref_id": 0})
    if want("diamond"):
        for r in db.query(DiamondLedger).filter(DiamondLedger.user_id == uid).order_by(
                DiamondLedger.created_at, DiamondLedger.id).all():
            rows.append({"time": r.created_at, "kind": "diamond", "kind_name": "钻石",
                         "amount": r.amount, "balance_after": r.balance_after,
                         "reason": r.reason, "ref_id": r.ref_id})
    if want("makeup"):
        card = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
        bal = card.balance if card else 0
        usage = db.query(MakeupUsageLog).filter(MakeupUsageLog.user_id == uid).order_by(
            MakeupUsageLog.used_at).all()
        running = bal + len(usage)  # 回推每次使用前的余额
        for r in usage:
            running -= 1
            rows.append({"time": r.used_at, "kind": "makeup", "kind_name": "补签卡",
                         "amount": -1, "balance_after": running,
                         "reason": f"补签 {r.target_date}（{r.status}）", "ref_id": r.task_id or 0})
    if want("coupon"):
        for r in db.query(RewardCoupon).filter(RewardCoupon.user_id == uid).all():
            rows.append({"time": r.created_at, "kind": "coupon", "kind_name": "卡券",
                         "amount": r.granted_count,
                         "balance_after": r.granted_count - r.redeemed_count,
                         "reason": f"{r.title}（已兑换 {r.redeemed_count}/{r.granted_count}，类型 {r.kind}）",
                         "ref_id": r.id})

    rows.sort(key=lambda x: x["time"] or datetime.min, reverse=True)
    total = len(rows)
    start = max(0, (page - 1) * page_size)
    items = rows[start:start + page_size]
    for r in items:
        r["time"] = r["time"].strftime("%Y-%m-%d %H:%M") if r["time"] else ""
    # 当前持有量汇总
    coin_bal = db.query(func.sum(CoinLedger.amount)).filter(CoinLedger.user_id == uid).scalar() or 0
    dia_acc = db.query(DiamondAccount).filter(DiamondAccount.user_id == uid).first()
    dia_bal = dia_acc.balance if dia_acc else 0.0
    mk = db.query(MakeupCard).filter(MakeupCard.user_id == uid).first()
    mk_bal = mk.balance if mk else 0
    return {"total": total, "page": page, "page_size": page_size, "items": items,
            "balance": {"coin": int(coin_bal), "diamond": round(dia_bal, 2), "makeup": mk_bal}}


# ═══════════════ 运营数据分析 ═══════════════

@router.get("/analytics", summary="运营数据分析（注册/活跃/留存/资产/AI/功能活跃）")
def analytics(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    today = date.today()
    start7 = datetime.combine(today - timedelta(days=6), datetime.min.time())
    start30 = datetime.combine(today - timedelta(days=29), datetime.min.time())

    total_users = db.query(func.count(User.id)).scalar() or 0
    new_7 = db.query(func.count(User.id)).filter(User.created_at >= start7).scalar() or 0
    new_30 = db.query(func.count(User.id)).filter(User.created_at >= start30).scalar() or 0

    # DAU：近 7 天（按 last_login_date）
    dau_map = dict(db.query(User.last_login_date, func.count(User.id)).filter(
        User.last_login_date >= today - timedelta(days=6)).group_by(
        User.last_login_date).all())
    active_trend = [{"date": (today - timedelta(days=i)).isoformat(),
                     "count": dau_map.get(today - timedelta(days=i), 0)}
                    for i in range(6, -1, -1)]
    dau_today = dau_map.get(today, 0)

    # 注册趋势：近 30 天
    reg_rows = db.query(func.date(User.created_at).label("d"), func.count(User.id)).filter(
        User.created_at >= start30).group_by("d").all()
    reg_map = {str(d): c for d, c in reg_rows}
    registration_trend = [{"date": (today - timedelta(days=i)).isoformat(),
                           "count": reg_map.get((today - timedelta(days=i)).isoformat(), 0)}
                          for i in range(29, -1, -1)]

    # 次留：近 14 天注册用户在注册次日仍活跃的比例
    retention = []
    for i in range(13, -1, -1):
        reg_date = today - timedelta(days=i + 1)
        day_start = datetime.combine(reg_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        reg_n = db.query(func.count(User.id)).filter(
            User.created_at >= day_start, User.created_at < day_end).scalar() or 0
        retained = 0
        if reg_n:
            retained = db.query(func.count(User.id)).filter(
                User.created_at >= day_start, User.created_at < day_end,
                User.last_login_date >= reg_date + timedelta(days=1)).scalar() or 0
        retention.append({"date": reg_date.isoformat(), "registered": reg_n,
                          "retained": retained,
                          "rate": round(retained / reg_n * 100, 1) if reg_n else 0.0})

    vip_count = db.query(func.count(VipUser.user_id)).scalar() or 0

    # 资产总量
    diamond_total = round(float(db.query(func.sum(DiamondAccount.balance)).scalar() or 0), 2)
    coin_total = int(db.query(func.sum(CoinLedger.amount)).scalar() or 0)
    makeup_total = int(db.query(func.sum(MakeupCard.balance)).scalar() or 0)

    # 资产流向
    def _flow(model, col, positive, since):
        q = db.query(func.sum(col)).filter(model.user_id.isnot(None))
        if positive:
            q = q.filter(col > 0)
        else:
            q = q.filter(col < 0)
        q = q.filter(getattr(model, "created_at") >= since)
        val = q.scalar() or 0
        return round(float(val), 2) if positive else round(abs(float(val)), 2)

    asset_flow = {
        "diamond_grant_7d": _flow(DiamondLedger, DiamondLedger.amount, True, start7),
        "diamond_spend_7d": _flow(DiamondLedger, DiamondLedger.amount, False, start7),
        "diamond_grant_30d": _flow(DiamondLedger, DiamondLedger.amount, True, start30),
        "diamond_spend_30d": _flow(DiamondLedger, DiamondLedger.amount, False, start30),
        "coin_grant_7d": int(_flow(CoinLedger, CoinLedger.amount, True, start7)),
        "coin_spend_7d": int(_flow(CoinLedger, CoinLedger.amount, False, start7)),
        "coin_grant_30d": int(_flow(CoinLedger, CoinLedger.amount, True, start30)),
        "coin_spend_30d": int(_flow(CoinLedger, CoinLedger.amount, False, start30)),
    }

    # AI 用量（近 30 天）
    ai_total = db.query(func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= start30).scalar() or 0
    ai_by_feature = [{"feature": f, "count": c} for f, c in db.query(
        AIUsageLog.feature, func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= start30).group_by(AIUsageLog.feature).all()]
    ai_by_provider = [{"provider": p, "count": c} for p, c in db.query(
        AIUsageLog.provider, func.count(AIUsageLog.id)).filter(
        AIUsageLog.created_at >= start30).group_by(AIUsageLog.provider).all()]

    # 各功能活跃（近 30 天）
    def _cnt(model, col, since):
        return db.query(func.count(getattr(model, col))).filter(
            getattr(model, "created_at") >= since).scalar() or 0

    feature_activity = [
        {"name": "做题（试卷）", "count": _cnt(ExamAttempt, "id", start30)},
        {"name": "错题标记", "count": db.query(func.count(WrongRecord.id)).filter(
            WrongRecord.wrong_at >= start30).scalar() or 0},
        {"name": "古诗文背诵", "count": db.query(func.count(ClassicalDailyLog.id)).filter(
            ClassicalDailyLog.learn_date >= today - timedelta(days=29)).scalar() or 0},
        {"name": "背单词", "count": db.query(func.count(VocabDailyLog.id)).filter(
            VocabDailyLog.learn_date >= today - timedelta(days=29)).scalar() or 0},
        {"name": "挑战赛刷题", "count": _cnt(ChallengeRecord, "id", start30)},
        {"name": "AI 对话/讲解", "count": _cnt(AiQa, "id", start30)},
        {"name": "家长留言", "count": _cnt(ParentMessage, "id", start30)},
    ]

    # 活跃榜：按近 30 天做题次数 Top10
    top_users = [{"user_id": u, "count": c} for u, c in db.query(
        ExamAttempt.user_id, func.count(ExamAttempt.id).label("c")).filter(
        ExamAttempt.created_at >= start30).group_by(ExamAttempt.user_id).order_by(
        func.count(ExamAttempt.id).desc()).limit(10).all()]

    return {
        "overview": {
            "total_users": total_users, "new_users_7d": new_7, "new_users_30d": new_30,
            "vip_count": vip_count, "dau_today": dau_today,
            "diamond_total": diamond_total, "coin_total": coin_total, "makeup_total": makeup_total,
        },
        "registration_trend": registration_trend,
        "active_trend": active_trend,
        "retention": retention,
        "asset_flow": asset_flow,
        "ai_usage": {"total_30d": ai_total, "by_feature": ai_by_feature,
                     "by_provider": ai_by_provider},
        "feature_activity": feature_activity,
        "top_users": top_users,
    }
