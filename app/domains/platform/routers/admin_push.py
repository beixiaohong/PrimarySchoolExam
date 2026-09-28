"""管理后台：消息推送（OneSignal Web Push）

- GET  /api/admin/push/status  通道是否就绪 + 订阅概况
- POST /api/admin/push/send    群发（全体 / 指定用户 / 按年级）
- POST /api/admin/push/test    给指定用户发一条测试推送
- GET  /api/admin/push/logs    最近发送记录（审计）

权限沿用运营组的 `announcement:manage`（与「系统公告」同一权限点）——
不为推送新造权限点，否则 RBAC 严格模式下新权限点默认无人拥有，
会出现「功能上线了但谁也点不动」的静默故障。

🚫 不注入 `db` 参数：发送是外部 HTTP 调用，会话必须短开短闭（见 services/push.py）。
所有写操作在发送完成后用独立短会话落审计日志。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.permissions import require_perm
from app.routers.admin import _audit, _require_admin

from ..services import push

logger = logging.getLogger(__name__)

router = APIRouter()

# 按年级群发的单次上限：避免一个大年级把 OneSignal 单请求打满
# （external_id 单请求上限 20000，但 5000 已远超本系统的实际年级人数）
GRADE_FANOUT_CAP = 5000


class SendReq(BaseModel):
    """群发请求：target=all 走段推送；user/grade 走 external_id 定向。"""
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=500)
    url: str = ""
    target: str = "all"              # all=全体订阅者 / user=指定用户 / grade=按年级
    user_ids: list = Field(default_factory=list)
    grade: int | None = None
    event: str = push.EVENT_BROADCAST


class TestReq(BaseModel):
    """测试推送：必须指定接收用户（不传则报 400，避免误发全体）。"""
    user_id: str = Field(min_length=1)
    title: str = "智学学堂 · 测试推送"
    body: str = "这是一条来自管理后台的测试推送。"


@router.get("/push/status", summary="推送通道状态与订阅概况")
def admin_push_status(admin=Depends(_require_admin)):
    """后台首页展示：通道是否就绪、已订阅设备数、可推送的事件类型。

    密钥只回传「是否已配置」，不回传明文（`_mask` 脱敏规则在 /config 接口里，
    此处连脱敏值都不给，避免后台页面 DOM 里残留密钥片段）。
    """
    cfg = push.push_sdk_config()
    stats = push.subscription_stats()
    return {
        "enabled": cfg["enabled"],
        "configured": {
            "app_id": bool(cfg["app_id"]),
            "rest_api_key": push.push_configured(),
            "safari_web_id": bool(cfg["safari_web_id"]),
        },
        "stats": stats,
        "events": [{"value": k, "label": v} for k, v in cfg["events"]],
    }


@router.post("/push/send", summary="群发推送",
             dependencies=[Depends(require_perm("announcement:manage",
                                                audit_action="推送群发",
                                                high_risk=True,
                                                audit_target_type="push"))])
def admin_push_send(req: SendReq, admin=Depends(_require_admin)):
    """向目标人群推送。

    - target=all：用 OneSignal 预置分段（`push.SEGMENT_ALL_SUBSCRIBERS`）一次广播，
      **不逐个过滤用户偏好**（运营公告属必达级别；也避免为上万人拼一个巨大请求）。
      返回的 recipients 是 OneSignal 侧实际触达的订阅数。
      ⚠️ 该分段名由 OneSignal 侧维护、会变；失效时接口返回 200 但无 id，
      现象等同「没人订阅」—— 群发突然 0 触达时先核对段名（见 push.py 常量处注释）。
    - target=user/grade：按 external_id 定向，逐用户**尊重偏好开关与免打扰时段**。

    返回：{ok, sent, recipients, skipped, reason, message}。
    """
    if not push.push_configured():
        raise HTTPException(400, "推送通道未配置：请先在「三方配置 → 消息推送」"
                                 "填写 ONESIGNAL_APP_ID 与 ONESIGNAL_REST_API_KEY")

    event = req.event if req.event in push.EVENTS else push.EVENT_BROADCAST
    if req.target == "all":
        res = push.send_to_all(req.title, req.body, url=req.url, event=event,
                               data={"from": "admin_broadcast"})
        target_desc = "全体订阅者"
    else:
        uids = [str(u).strip() for u in (req.user_ids or []) if str(u or "").strip()]
        if req.target == "grade":
            if not req.grade:
                raise HTTPException(400, "按年级群发需要传 grade")
            uids = _user_ids_of_grade(int(req.grade))
            if not uids:
                raise HTTPException(404, "该年级没有用户")
        if not uids:
            raise HTTPException(400, "没有接收者：user 目标需传 user_ids")
        if len(uids) > GRADE_FANOUT_CAP:
            raise HTTPException(400, "单次推送人数上限 %d，请分批发送" % GRADE_FANOUT_CAP)
        res = push.send_to_users(uids, req.title, req.body, url=req.url, event=event,
                                 data={"from": "admin_send"})
        target_desc = "%d 人（%s）" % (len(uids), {"user": "指定用户",
                                                   "grade": "年级 %s" % req.grade}.get(
            req.target, req.target))

    # 审计：发送之后落库（独立短会话），失败不影响已发出的推送结果
    from app.database import SessionLocal
    try:
        with SessionLocal() as db:
            _audit(db, admin, "push:send", target=req.target,
                   detail="推送「%s」→ %s，成功 %s 人" % (req.title[:40], target_desc,
                                                        res.get("sent", 0)),
                   target_type="push")
    except Exception as e:                            # noqa: BLE001
        logger.warning("推送审计日志写入失败：%s", e)

    out = dict(res)
    out["target_desc"] = target_desc
    if not res.get("ok"):
        out["hint"] = {
            "no_subscription": "目标人群里没有有效订阅（用户未授权浏览器通知）",
            "http_error": "OneSignal 返回错误，请核对密钥与 App ID 是否属于同一个应用",
        }.get(res.get("reason", ""), "")
    return out


@router.post("/push/test", summary="给指定用户发测试推送",
             dependencies=[Depends(require_perm("announcement:manage",
                                                audit_action="推送测试"))])
def admin_push_test(req: TestReq, admin=Depends(_require_admin)):
    """排查用：只发给一个用户，验证「密钥是否正确、该用户是否已授权」。"""
    if not push.push_configured():
        raise HTTPException(400, "推送通道未配置")
    res = push.notify_user(req.user_id.strip(), req.title, req.body,
                           url="/#/settings", event=push.EVENT_TEST,
                           data={"from": "admin_test", "by": admin.username})
    return res


@router.get("/push/logs", summary="最近推送记录")
def admin_push_logs(limit: int = 50, event: str = "", admin=Depends(_require_admin)):
    """审计用：最近的推送发送记录（含成功/失败与 OneSignal 错误）。"""
    return {"items": push.recent_logs(limit=limit, event=event)}


def _user_ids_of_grade(grade: int) -> list:
    """按年级取用户 ID 列表（独立短会话；只读）"""
    from app.database import SessionLocal
    from app.models.user import User

    with SessionLocal() as db:
        rows = (db.query(User.user_id)
                .filter(User.grade == grade)
                .limit(GRADE_FANOUT_CAP).all())
    return [r[0] for r in rows if r[0]]
