"""推送通知接口（用户端，OneSignal Web Push）

- GET  /api/push/config      前端初始化所需的公开配置（App ID / 开关 / 我的偏好与订阅）
- POST /api/push/subscribe   上报 OneSignal subscription id（登录后 / 授权后）
- POST /api/push/unsubscribe 解绑（登出时；可只解绑当前设备）
- GET  /api/push/status      当前用户订阅与偏好概览
- GET  /api/push/prefs       读偏好
- PUT  /api/push/prefs       改偏好（逐场景开关 + 免打扰时段）
- POST /api/push/test        给自己发一条测试推送（验证端到端是否通）

🚫 本模块**不注入 `db: Session = Depends(get_db)`**（与 platform/routers/ai.py 同范式）：
发送推送是外部 HTTP 调用，若在请求级会话打开期间进行，会长时间占用连接池连接，
历史上曾因此耗尽 QueuePool 导致全站超时。服务层自己开短会话，HTTP 在会话之外。

鉴权：挂载时统一加 `user_auth_deps`（require_self，严格账号绑定）；
这里再用 `require_user` 取当前登录用户，**不采信前端传来的 user_id**，
避免「传别人的 user_id 就能给别人推消息/改他偏好」的越权。
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# 跨域取当前登录用户：必须经 identity 域的 contracts（.importlinter 强制），
# 不得直接 import app.domains.identity.routers.auth
from app.domains.identity.contracts import require_user
from app.models.user import User

from ..services import push

logger = logging.getLogger(__name__)

router = APIRouter()

# 与 push_logs.body / push_logs.title 的列长一致，入口就先挡住超长内容
TITLE_MAX = 120
BODY_MAX = 500


class SubscribeReq(BaseModel):
    """上报订阅：subscription_id 来自前端 `OneSignal.User.PushSubscription.id`"""
    subscription_id: str = Field(min_length=1, max_length=64)
    platform: str = "web"        # web / miniapp / app（后两者为预留通道）
    device_type: str = ""
    browser: str = ""
    user_agent: str = ""
    opted_in: bool = True


class UnsubscribeReq(BaseModel):
    """解绑：不传 subscription_id 则解绑该用户全部设备（登出场景）"""
    subscription_id: str = ""


class PrefsReq(BaseModel):
    """偏好更新：仅传需要改的字段（None = 不动）"""
    enable_study: bool | None = None
    enable_im: bool | None = None
    enable_announce: bool | None = None
    enable_exam: bool | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None


@router.get("/config", summary="推送前端配置（含我的偏好与订阅状态）")
def push_config(user: User = Depends(require_user)):
    """前端初始化用：通道开关 + App ID + 我的偏好与已订阅设备数。

    `enabled=False` 时前端**不加载 OneSignal SDK**、也不展示推送设置项 ——
    避免用户开了开关却永远收不到（这类问题最难排查）。
    """
    cfg = push.push_sdk_config()
    prefs = push.get_prefs(user.user_id)
    stats = push.subscription_stats()
    return {
        "enabled": cfg["enabled"],
        "app_id": cfg["app_id"],
        "safari_web_id": cfg["safari_web_id"],
        "events": cfg["events"],
        "prefs": prefs,
        # 全站订阅数仅作参考，前端只用它显示「已授权设备」
        "total_subscriptions": stats["subscriptions"],
    }


@router.post("/subscribe", summary="上报推送订阅（登录后/授权后）")
def subscribe(req: SubscribeReq, user: User = Depends(require_user)):
    """登记或更新一条订阅。

    同一 subscription_id 重复上报按更新处理（换账号登录时改写归属），
    否则同一台电脑换账号后，旧账号会继续收到推送。
    """
    res = push.register_subscription(
        user_id=user.user_id, subscription_id=req.subscription_id,
        platform=req.platform, device_type=req.device_type, browser=req.browser,
        user_agent=req.user_agent, opted_in=req.opted_in)
    if not res.get("ok"):
        return {"ok": False, "message": res.get("message", "订阅登记失败")}
    return {"ok": True, "subscription_id": res["subscription_id"]}


@router.post("/unsubscribe", summary="解绑推送订阅（登出时）")
def unsubscribe(req: UnsubscribeReq, user: User = Depends(require_user)):
    """解绑当前设备（传 subscription_id）或全部设备（不传）。

    登出必须解绑：否则公共电脑上退出账号后，下一位使用者会看到
    「某某的学习提醒」通知，既是隐私泄露也伤害体验。
    """
    res = push.revoke_subscription(user.user_id, req.subscription_id)
    return {"ok": True, "revoked": res.get("revoked", 0)}


@router.get("/status", summary="我的推送状态")
def push_status(user: User = Depends(require_user)):
    """通道是否可用 + 我的偏好 + 已登记的有效订阅数。"""
    from app.database import SessionLocal
    from app.models.push import PushSubscription

    with SessionLocal() as db:
        n = (db.query(PushSubscription)
             .filter(PushSubscription.user_id == user.user_id,
                     PushSubscription.revoked_at.is_(None)).count())
    cfg = push.push_sdk_config()
    return {"enabled": cfg["enabled"], "subscribed_devices": n,
            "prefs": push.get_prefs(user.user_id)}


@router.get("/prefs", summary="读推送偏好")
def get_prefs(user: User = Depends(require_user)):
    return push.get_prefs(user.user_id)


@router.put("/prefs", summary="改推送偏好（逐场景开关 + 免打扰时段）")
def save_prefs(req: PrefsReq, user: User = Depends(require_user)):
    """保存偏好。未传的字段不动；免打扰时段非法值会被服务层归一为「不启用」。"""
    return push.save_prefs(
        user.user_id, enable_study=req.enable_study, enable_im=req.enable_im,
        enable_announce=req.enable_announce, enable_exam=req.enable_exam,
        quiet_start=req.quiet_start, quiet_end=req.quiet_end)


@router.post("/test", summary="给自己发一条测试推送")
def push_test(user: User = Depends(require_user)):
    """验证端到端链路：浏览器授权 -> external_id 绑定 -> 后端下发。

    返回 reason 便于自助排查：
    - not_configured：后台未填 APP_ID / REST_API_KEY，或 PUSH_ENABLED=false
    - no_subscription：没有有效订阅（多为浏览器未授权，或授权后未刷新页面）
    """
    res = push.notify_user(
        user.user_id, "智学学堂 · 测试推送",
        "如果你看到这条通知，说明推送已经打通。可在「设置 - 消息推送」里调整提醒类型。",
        url="/#/settings", event=push.EVENT_TEST, data={"from": "self_test"})
    if res.get("ok"):
        return {"ok": True, "message": "已发送，请查看系统通知（约 1-3 秒）"}
    return {"ok": False, "reason": res.get("reason", ""),
            "message": {
                "not_configured": "推送通道未配置，请先在管理后台填写 OneSignal 密钥",
                "no_subscription": "没有找到有效订阅：请在浏览器弹窗中允许通知，然后重试",
                "http_error": "OneSignal 返回错误：%s" % res.get("message", ""),
                "request_failed": "请求 OneSignal 失败，请稍后重试",
                "audience_error": "服务异常，请稍后重试",
            }.get(res.get("reason", ""), res.get("message") or "发送失败")}
