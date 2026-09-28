"""推送通知服务（OneSignal Web Push；发送链路按平台无关设计，预留小程序 / App）

定位：与 `mailer.send_email` / `sms.send_sms` 并列的**第三条通知通道**，属 D8 平台域。
其它域（frozen 的 IM、assessment 的成绩等）一律经 `platform.contracts` 调用，
不得直连本模块。

设计要点
1. 「尽力而为」：推送失败绝不影响主流程（发消息、交卷、发公告都必须成功）。
   所有对外函数**不抛异常**，失败只记日志并返回 `{ok: False, ...}`。
2. 🚨 **不持 DB 连接**：本模块自己开短会话读偏好/写日志，HTTP 调用一律在会话之外。
   调用方**不得**把请求级 `db` 会话传进来（那样整个 HTTP 期间都占着连接池，
   历史上曾因此耗尽 QueuePool 导致全站超时）。需要 DB 的只有两处：
   `_load_prefs`（读偏好 + 当日计数）与 `_write_logs`（写发送记录），各自独立短会话。
3. 定向靠 `external_id`：OneSignal 侧 external_id 就是本系统的 `user_id`，
   前端登录时 `OneSignal.login(user_id)` 绑定、登出 `logout()` 解绑。
   本模块不强依赖 `push_subscriptions` 表是否登记过 —— 表用于解绑与统计，
   发送只认 external_id，避免「用户没上报订阅 -> 一条都收不到」的静默故障。
4. 防打扰三闸：用户场景开关 → 免打扰时段 → 每人每日上限（见 `DAILY_CAP`）。
   自动事件（学习提醒/私信/成绩）受限；运营类（公告/群发）不占额度，
   否则一条公告就能把用户的每日额度吃光，后续真实提醒全被吞掉。
"""
import logging
from datetime import datetime, timedelta

import requests

from app.domains.platform.services import sysconfig

logger = logging.getLogger(__name__)

# OneSignal REST API（Create message）。旧版 /api/v1/notifications 已废弃。
ONESIGNAL_API = "https://api.onesignal.com/notifications"
HTTP_TIMEOUT = 10        # 秒。推送是尽力而为，宁可快速失败也不拖住业务请求
BATCH_SIZE = 1000        # 单请求 external_id 上限 20000；取 1000 便于失败时定位批次
MAX_LOG_ROWS = 200       # 超过则只写一行汇总，避免群发写出几千行日志
DAILY_CAP = 8            # 自动事件每人每日上限；公告/群发（announce/broadcast）不受限

# 群发（broadcast）用的 OneSignal 预置分段名。
#
# ⚠️ 不要在 payload 里写段名字面量。OneSignal 调整过预置段的命名（从「用户」维度改为
# 「订阅」维度），旧名 `Subscribed Users` 已不存在 —— 而**段名失效时接口返回 200、却不带 id**，
# 现象与「没有任何订阅者」完全一样，极易把排查带偏（2026-09-28 实际踩过：
# 后台群发一直「0 人 / no_subscription」，真因是段名过期，而非没人订阅）。
#
# 核对手册（只读，不打印任何密钥）：
#   GET https://api.onesignal.com/apps/{app_id}/segments        → 列出全部段名
#   GET https://api.onesignal.com/apps/{app_id}/segments/{sid}  → {"subscriber_count": N}
# 群发「0 人」时的第一步就是跑上面两条，先确认段名仍然存在。
SEGMENT_ALL_SUBSCRIBERS = "Total Subscriptions"   # 全部已授权订阅者（含各渠道）

# ── 事件常量（与前端 push.js、prefs 字段、push_logs.event 三处对齐）──
EVENT_STUDY = "study"          # 学习提醒：作业 / 打卡 / 复习
EVENT_IM = "im"                # 私信离线提醒
EVENT_ANNOUNCE = "announce"    # 公告与站内信
EVENT_EXAM = "exam"            # 考试与成绩
EVENT_BROADCAST = "broadcast"  # 后台手动群发
EVENT_TEST = "test"            # 用户/后台自测

EVENTS = (EVENT_STUDY, EVENT_IM, EVENT_ANNOUNCE, EVENT_EXAM, EVENT_BROADCAST, EVENT_TEST)

# 事件 → 用户偏好字段（未登记的（如 test）视为总是允许）
_PREF_FIELD = {
    EVENT_STUDY: "enable_study",
    EVENT_IM: "enable_im",
    EVENT_ANNOUNCE: "enable_announce",
    EVENT_EXAM: "enable_exam",
}

# 不占每日额度的运营类事件
_UNLIMITED_EVENTS = (EVENT_ANNOUNCE, EVENT_BROADCAST)

_EVENT_LABELS = {
    EVENT_STUDY: "学习提醒",
    EVENT_IM: "私信提醒",
    EVENT_ANNOUNCE: "公告通知",
    EVENT_EXAM: "考试通知",
    EVENT_BROADCAST: "后台群发",
    EVENT_TEST: "测试推送",
}


def event_label(event: str) -> str:
    """事件中文名（后台展示用）"""
    return _EVENT_LABELS.get(event, event or "通知")


# ─────────────────────────── 配置读取 ───────────────────────────

def _app_id() -> str:
    """OneSignal App ID（后台「三方配置」可覆盖 .env）"""
    return (sysconfig.get("ONESIGNAL_APP_ID", "") or "").strip()


def _rest_key() -> str:
    """OneSignal REST API Key（机密，仅后端使用）"""
    return (sysconfig.get("ONESIGNAL_REST_API_KEY", "") or "").strip()


def _safari_web_id() -> str:
    return (sysconfig.get("ONESIGNAL_SAFARI_WEB_ID", "") or "").strip()


def _enabled() -> bool:
    """总开关：PUSH_ENABLED 非 false 即为开（默认开，缺失按开处理）"""
    return (sysconfig.get("PUSH_ENABLED", "true") or "true").strip().lower() not in (
        "0", "false", "no", "off")


def push_configured() -> bool:
    """推送通道是否可用：总开关开 + APP_ID + REST_API_KEY 都已配置

    三者缺一即整体降级为「不发送」，前端也不加载 SDK —— 与 `sms_configured`
    同构，调用方不必自己判断配置完整性。
    """
    return bool(_enabled() and _app_id() and _rest_key())


def push_sdk_config() -> dict:
    """下发给前端的公开配置（**绝不含 REST_API_KEY**）"""
    return {
        "enabled": push_configured(),
        "app_id": _app_id() if push_configured() else "",
        "safari_web_id": _safari_web_id(),
        # 前端据此决定是否展示推送设置项：通道没配置就整块隐藏，
        # 避免用户开了开关却永远收不到任何东西（最难排查的一类投诉）
        # 与 /api/admin/push/status 用同一种 {value,label} 结构，避免两处前端各写一套解析
        "events": [{"value": k, "label": v} for k, v in _EVENT_LABELS.items()],
    }


def _base_url() -> str:
    """站点根地址（推送 url 必须是绝对地址，OneSignal 会原样带进通知）

    ⚠️ 默认值必须与 OneSignal 后台的 `chrome_web_origin` 一致，且指向**主域名**。
    `www.x.com` 与 `x.com` 是两个独立 origin：通知 url 若落在另一个源，用户点开时
    登录态（localStorage）不在那边，表现为「点开通知是未登录」。
    本项目主域名以 **www** 为准（与 nginx 证书目录、OneSignal 配置一致）。
    """
    base = (sysconfig.get("SITE_URL", "") or "").strip() or "https://www.liusijin.com"
    return base.rstrip("/")


def abs_url(path: str) -> str:
    """相对路径补成绝对地址；空值返回空串（不传 url 字段）"""
    if not path:
        return ""
    p = path.strip()
    if p.startswith("http://") or p.startswith("https://"):
        return p
    return _base_url() + ("" if p.startswith("/") else "/") + p


# ─────────────────────────── 偏好与限额 ───────────────────────────

def _cut(value, limit: int) -> str:
    """写库前截断，避免超长字符串直接报错（宁可截断也不要丢整条日志）"""
    s = "" if value is None else str(value)
    return s[:limit]


def _parse_hhmm(text: str):
    """'21:30' → (21, 30)；非法返回 None"""
    try:
        hh, mm = str(text or "").strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:                                # noqa: BLE001
        pass
    return None


def in_quiet_hours(pref, now: datetime = None) -> bool:
    """是否处于用户自设的免打扰时段（两端任一为空则视为未启用）

    注意：这里的免打扰是**用户自愿**的推送静音，与平台的 `check_quiet_hours`
    （未成年人护眼宵禁，会拦截接口）语义不同，刻意不复用，避免互相干扰。
    """
    if pref is None:
        return False
    start = _parse_hhmm(getattr(pref, "quiet_start", ""))
    end = _parse_hhmm(getattr(pref, "quiet_end", ""))
    if not start or not end or start == end:
        return False
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute
    s, e = start[0] * 60 + start[1], end[0] * 60 + end[1]
    # 跨零点（如 22:00-07:00）时区间反向
    return (s <= cur < e) if s < e else (cur >= s or cur < e)


def pref_allows(pref, event: str) -> bool:
    """该用户偏好是否允许此类事件（无偏好行 = 全开）"""
    field = _PREF_FIELD.get(event)
    if not field or pref is None:
        return True
    return bool(getattr(pref, field, True))


def _load_audience(user_ids: list, event: str, dedup_key: str):
    """短会话：去重检查 + 偏好过滤 + 每日限额。返回 (allowed_ids, reason)

    DB 段必须独立且短 —— 本函数返回后即关闭会话，HTTP 发送在会话之外进行。
    """
    from app.database import SessionLocal
    from app.models.push import PushLog, PushPref

    ids = [str(u).strip() for u in (user_ids or []) if str(u or "").strip()]
    if not ids:
        return [], "no_recipient"
    # 同一批内先去重，避免重复入参把日志/计数写花
    ids = list(dict.fromkeys(ids))

    now = datetime.now()
    with SessionLocal() as db:
        # ① 幂等：同 dedup_key 已发过则直接跳过（定时任务重跑/接口重试的保护）
        if dedup_key:
            hit = db.query(PushLog.id).filter(PushLog.dedup_key == dedup_key).first()
            if hit:
                return [], "duplicate"

        # ② 偏好过滤：一次取回本批用户的偏好行（无行的用户按全开处理）
        rows = db.query(PushPref).filter(PushPref.user_id.in_(ids)).all()
        prefs = {r.user_id: r for r in rows}
        allowed, blocked_quiet = [], 0
        for uid in ids:
            p = prefs.get(uid)
            if not pref_allows(p, event):
                continue
            if in_quiet_hours(p, now):
                blocked_quiet += 1
                continue
            allowed.append(uid)

        # ③ 每日限额（仅自动事件）：查当天已成功发送的条数，超限的剔除
        if event not in _UNLIMITED_EVENTS and allowed:
            from sqlalchemy import func
            since = datetime(now.year, now.month, now.day)
            rows2 = (db.query(PushLog.user_id, func.count(PushLog.id))
                     .filter(PushLog.user_id.in_(allowed), PushLog.created_at >= since,
                             PushLog.ok.is_(True))
                     .group_by(PushLog.user_id).all())
            hit_ids = {u for u, n in rows2 if (n or 0) >= DAILY_CAP}
            if hit_ids:
                allowed = [u for u in allowed if u not in hit_ids]

    if not allowed:
        return [], ("quiet_hours" if blocked_quiet else "all_filtered")
    return allowed, ""


def _write_logs(rows: list):
    """短会话写发送记录（失败只记日志：日志写不进去不该让发送结果变假）"""
    if not rows:
        return
    from app.database import SessionLocal
    from app.models.push import PushLog

    try:
        with SessionLocal() as db:
            db.add_all([PushLog(**r) for r in rows])
            db.commit()
    except Exception as e:                            # noqa: BLE001
        logger.warning("推送日志写入失败（不影响发送）：%s", e)


# ─────────────────────────── 发送 ───────────────────────────

def _post(payload: dict):
    """纯 HTTP 调用（**不碰 DB**）。返回 (ok, status, body_dict, error_text)"""
    try:
        resp = requests.post(
            ONESIGNAL_API,
            json=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": "Key %s" % _rest_key()},
            timeout=HTTP_TIMEOUT,
        )
        status = resp.status_code
        try:
            body = resp.json()
        except Exception:                             # noqa: BLE001
            body = {}
        if status in (200, 201):
            return True, status, body, ""
        err = (body.get("errors") if isinstance(body, dict) else "") or resp.text
        return False, status, body, _cut(err, 255)
    except Exception as e:                            # noqa: BLE001
        return False, 0, {}, _cut(e, 255)


def _parse_resp(ok: bool, resp_body, err: str = "") -> tuple:
    """解析 OneSignal 响应 → (ok, msg_id, recipients, err)

    **关键约定：HTTP 2xx 但没有 `id` = 靶向受众里没有有效订阅**（用户没授权、或已解绑）。
    这种情况必须判定为**失败** —— 否则前端会提示「已发送」而用户永远收不到，
    属于最难排查的一类「假成功」。

    抽成公共函数的原因：定向发送（`_send_once`）与段推送（`send_to_all`）本是两条路径，
    段推送漏了这段判定，于是同一件事在后台表现为「结果=失败、错误=空」外加接口回「已广播」——
    正是这次线上群发踩到的坑。统一到一处，避免再次漂移。
    """
    msg_id = ""
    recipients = 0
    if isinstance(resp_body, dict):
        msg_id = _cut(resp_body.get("id") or "", 64)
        try:
            recipients = int(resp_body.get("recipients") or 0)
        except Exception:                             # noqa: BLE001
            recipients = 0
    if ok and not msg_id:
        ok = False
        err = err or "no_subscription"
    return ok, msg_id, recipients, err


def _send_once(external_ids: list, title: str, body: str, url: str,
               event: str, data: dict) -> tuple:
    """发一批（≤BATCH_SIZE 个 external_id）。返回 (ok, status, onesignal_id, recipients, err)"""
    payload = {
        "app_id": _app_id(),
        "target_channel": "push",
        # OneSignal 侧 external_id == 本系统 user_id（前端 login 时绑定）
        "include_aliases": {"external_id": external_ids},
        "headings": {"en": title, "zh-Hans": title},
        "contents": {"en": body, "zh-Hans": body},
    }
    if url:
        payload["url"] = url
    payload["data"] = dict(data or {}, event=event)
    ok, status, resp_body, err = _post(payload)
    ok, msg_id, recipients, err = _parse_resp(ok, resp_body, err)
    return ok, status, msg_id, recipients, err


def send_to_users(user_ids: list, title: str, body: str, url: str = "",
                  event: str = EVENT_BROADCAST, data: dict = None,
                  dedup_key: str = "", log_per_user: bool = True) -> dict:
    """向指定用户推送（按 external_id 定向）。**永不抛异常**。

    参数：
        user_ids：接收者 user_id 列表（内部去重、过滤偏好与限额）
        title/body：标题与正文（超长自动截断到库字段上限）
        url：点击跳转地址，相对路径会自动补成绝对地址
        event：事件类型（决定走哪个偏好开关、是否占每日额度）
        data：附加数据（随通知带回前端，便于排查）
        dedup_key：幂等键，非空时同键只发一次
        log_per_user：是否逐用户写明细日志。False 时只写一行汇总 ——
            供 `send_per_user_dedup` 使用，避免它再写一遍带 dedup_key 的记录
            导致同一用户当天出现两行 ok=True 日志、把每日限额算成双倍。

    返回：{ok, sent, recipients, skipped, reason, message}
        ok=False 的 reason 取值：
        - not_configured：通道未配置（未填 App ID / Key，或 PUSH_ENABLED=false）
        - duplicate：dedup_key 命中，已发过
        - all_filtered / quiet_hours：全部被偏好或免打扰挡掉
        - no_recipient：入参为空
        - http_error / request_failed：OneSignal 报错或网络异常
    """
    title_s, body_s = _cut(title, 120), _cut(body, 500)
    if not push_configured():
        logger.info("推送通道未配置，跳过发送（event=%s, %d 人）", event, len(user_ids or []))
        return {"ok": False, "sent": 0, "recipients": 0, "skipped": len(user_ids or []),
                "reason": "not_configured", "message": "推送通道未配置"}

    # 受众筛选要读 DB（偏好/去重/限额）：DB 异常绝不能把业务主流程炸掉，
    # 这里就地兜住 —— 「永不抛异常」是本模块对调用方的承诺。
    try:
        targets, reason = _load_audience(user_ids, event, dedup_key)
    except Exception as e:                            # noqa: BLE001
        logger.warning("推送受众筛选失败（已跳过本次推送）：%s", e)
        return {"ok": False, "sent": 0, "recipients": 0, "skipped": len(user_ids or []),
                "reason": "audience_error", "message": _cut(e, 200)}
    if not targets:
        if dedup_key and reason == "duplicate":
            logger.info("推送已发过（dedup_key=%s），跳过", dedup_key)
        return {"ok": False, "sent": 0, "recipients": 0,
                "skipped": len(user_ids or []), "reason": reason or "no_recipient",
                "message": "无有效接收者"}

    abs_url_ = abs_url(url)
    total_recipients = 0
    sent_ids, all_ok, last_status, last_err, last_msg_id = [], True, 0, "", ""
    for i in range(0, len(targets), BATCH_SIZE):
        chunk = targets[i:i + BATCH_SIZE]
        # dedup_key 只在最后一批写库：中途失败时允许重跑补发
        ok, status, msg_id, recipients, err = _send_once(
            chunk, title_s, body_s, abs_url_, event, data or {})
        last_status, last_err, last_msg_id = status, err, msg_id
        total_recipients += recipients
        if ok:
            sent_ids.extend(chunk)
        else:
            all_ok = False

    if sent_ids and (not dedup_key or all_ok):
        # 成功（或非去重场景）：写一行带 dedup_key 的汇总
        _write_logs([{
            "user_id": "", "event": event, "title": title_s, "body": body_s,
            "url": abs_url_, "dedup_key": dedup_key or None, "onesignal_id": last_msg_id,
            "recipients": total_recipients, "ok": all_ok, "http_status": last_status,
            "error": last_err,
        }])
    elif not sent_ids and (last_status or last_err):
        # 失败：也要留痕，否则后台看不到「为什么没发出去」（密钥错、无订阅者、网络异常）。
        # 刻意**不写 dedup_key**：去重键只在成功时占用，失败后重跑要能补发。
        _write_logs([{
            "user_id": "", "event": event, "title": title_s, "body": body_s,
            "url": abs_url_, "dedup_key": None, "onesignal_id": "",
            "recipients": total_recipients, "ok": False, "http_status": last_status,
            "error": last_err or "发送失败",
        }])

    # 逐用户明细（便于「我收到过什么」与每日计数），条数多时只留汇总行
    if log_per_user and sent_ids and len(sent_ids) <= MAX_LOG_ROWS:
        _write_logs([{
            "user_id": uid, "event": event, "title": title_s, "body": body_s,
            "url": abs_url_, "dedup_key": None, "onesignal_id": last_msg_id,
            "recipients": 1, "ok": True, "http_status": last_status, "error": "",
        } for uid in sent_ids])

    if sent_ids:
        reason = "" if all_ok else "http_error"
    elif last_err == "no_subscription":
        # 单列出来：这是「配置没问题，但没人订阅」——排查方向与密钥错误完全不同
        reason = "no_subscription"
    else:
        reason = "http_error" if last_status else "request_failed"
    result = {
        "ok": bool(sent_ids) and all_ok,
        "sent": len(sent_ids),
        "recipients": total_recipients,
        "skipped": max(0, len(user_ids or []) - len(sent_ids)),
        "reason": reason,
        "message": last_err or ("已提交 %d 人" % len(sent_ids)),
    }
    if not sent_ids:
        logger.warning("推送发送失败：event=%s status=%s err=%s", event, last_status, last_err)
    else:
        logger.info("推送已提交：event=%s %d 人（触达订阅 %d）",
                    event, len(sent_ids), total_recipients)
    return result


def send_to_all(title: str, body: str, url: str = "", event: str = EVENT_BROADCAST,
                data: dict = None) -> dict:
    """向全部订阅者广播（不按 external_id 定向）。

    用于后台「全体群发」：无需先查全站用户列表，也避免把上万人塞进一次请求。
    `included_segments` 用 OneSignal 预置分段 `SEGMENT_ALL_SUBSCRIBERS`（全部已授权订阅者）。
    ⚠️ 段名会随 OneSignal 侧调整而失效，失效时接口**返回 200 但无 id**，看起来就像
    「没人订阅」—— 群发突然 0 触达时，先按常量处的注释核对段名，别急着下结论。
    """
    title_s, body_s = _cut(title, 120), _cut(body, 500)
    if not push_configured():
        return {"ok": False, "sent": 0, "recipients": 0, "skipped": 0,
                "reason": "not_configured", "message": "推送通道未配置"}
    payload = {
        "app_id": _app_id(),
        "target_channel": "push",
        "included_segments": [SEGMENT_ALL_SUBSCRIBERS],
        "headings": {"en": title_s, "zh-Hans": title_s},
        "contents": {"en": body_s, "zh-Hans": body_s},
        "data": dict(data or {}, event=event),
    }
    abs_url_ = abs_url(url)
    if abs_url_:
        payload["url"] = abs_url_
    ok, status, resp_body, err = _post(payload)
    ok, msg_id, recipients, err = _parse_resp(ok, resp_body, err)
    _write_logs([{
        "user_id": "", "event": event, "title": title_s, "body": body_s, "url": abs_url_,
        "dedup_key": None, "onesignal_id": msg_id, "recipients": recipients,
        "ok": ok, "http_status": status, "error": err,
    }])
    # 失败原因必须区分「没人订阅」与「OneSignal 报错」：前者是运营还没让用户授权，
    # 后者要核对密钥与 App ID 是否属于同一应用 —— 两者排查方向完全不同。
    # 口径与 send_to_users 的 reason 取值保持一致。
    if ok:
        reason, message = "", "已广播"
    elif err == "no_subscription":
        # 两种可能都必须提示：① 真的没人订阅；② OneSignal 侧该分段不存在或被改名。
        # 两者现象完全一样（200 但无 id），只提示前者会把排查方向带偏
        # （2026-09-28 实际踩过：群发一直 0 人，真因是段名过期而非没人订阅）。
        reason = "no_subscription"
        message = ("没有触达任何订阅者：目标人群尚未授权浏览器通知，"
                   "或 OneSignal 侧分段名已失效（核对方法见 SEGMENT_ALL_SUBSCRIBERS 注释）")
    else:
        reason, message = "http_error", (err or "OneSignal 返回错误")
    return {"ok": ok, "sent": recipients, "recipients": recipients,
            "skipped": 0, "reason": reason, "message": message}


def send_per_user_dedup(user_ids: list, title: str, body: str, url: str = "",
                        event: str = EVENT_BROADCAST, key_template: str = "",
                        data: dict = None) -> dict:
    """批量推送，但**每个用户一个独立去重键**（同一事件对同一用户当天只提醒一次）。

    场景：IM 离线提醒 —— 一个群聊里连发 10 条消息，离线成员不该收到 10 条推送，
    「这个会话今天提醒过一次就够了」。此时去重键里含用户与会话，
    无法用 `send_to_users` 的单一 dedup_key 表达。

    流程：一次查出已被去重的用户 → 批量发送（1 个 HTTP 请求覆盖多人，避免逐个发）
          → 给实际发出的用户逐条落 dedup_key 记录（下次调用即被挡住）。

    key_template 用 `{uid}` 作占位，例如 `im:{uid}:38:2026-09-28`。
    """
    ids = [str(u).strip() for u in (user_ids or []) if str(u or "").strip()]
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"ok": False, "sent": 0, "recipients": 0, "skipped": 0,
                "reason": "no_recipient", "message": "无接收者"}

    keys = {}
    if key_template:
        from app.database import SessionLocal
        from app.models.push import PushLog

        keys = {uid: _cut(key_template.replace("{uid}", uid), 120) for uid in ids}
        try:
            with SessionLocal() as db:
                done = {r[0] for r in db.query(PushLog.dedup_key)
                        .filter(PushLog.dedup_key.in_(list(keys.values()))).all()}
        except Exception as e:                        # noqa: BLE001
            # 去重表读不到时按「都没发过」处理：宁可多打扰一次，也不要静默不推
            logger.warning("逐人去重查询失败（本次按未发过处理）：%s", e)
            done = set()
        fresh = [u for u in ids if keys.get(u) not in done]
        if not fresh:
            return {"ok": False, "sent": 0, "recipients": 0, "skipped": len(ids),
                    "reason": "duplicate", "message": "已提醒过，跳过"}
    else:
        fresh = ids

    # log_per_user=False：避免与下面的 dedup 明细各写一行，
    # 否则每日限额会把同一用户算成两次
    res = send_to_users(fresh, title, body, url=url, event=event, data=data,
                        dedup_key="", log_per_user=False)
    if keys and res.get("sent"):
        _write_logs([{
            "user_id": uid, "event": event, "title": _cut(title, 120),
            "body": _cut(body, 500), "url": abs_url(url), "dedup_key": keys[uid],
            "onesignal_id": "", "recipients": 1, "ok": True, "http_status": 200,
            "error": "",
        } for uid in fresh[:MAX_LOG_ROWS]])
    res["skipped"] = max(res.get("skipped", 0), len(ids) - len(fresh))
    return res


def notify_user(user_id: str, title: str, body: str, url: str = "",
                event: str = EVENT_BROADCAST, data: dict = None,
                dedup_key: str = "") -> dict:
    """单人推送的便捷封装（其它域经 contracts 调用的常用形态）"""
    return send_to_users([user_id], title, body, url=url, event=event,
                         data=data, dedup_key=dedup_key)


def notify_users(user_ids: list, title: str, body: str, url: str = "",
                 event: str = EVENT_BROADCAST, data: dict = None,
                 dedup_key: str = "") -> dict:
    """多人推送（与 notify_user 同义，语义更清晰的别名）"""
    return send_to_users(user_ids, title, body, url=url, event=event,
                         data=data, dedup_key=dedup_key)


# ─────────────────────────── 订阅登记 ───────────────────────────

def register_subscription(user_id: str, subscription_id: str, platform: str = "web",
                          device_type: str = "", browser: str = "",
                          user_agent: str = "", opted_in: bool = True) -> dict:
    """登记/更新一条订阅（前端拿到 OneSignal subscription id 后上报）。

    同一 subscription_id 重复上报走更新（换用户登录时改写 user_id，
    这是「同一台电脑换账号」的正确行为 —— 否则旧账号会继续收到推送）。
    """
    from app.database import SessionLocal
    from app.models.push import PushSubscription

    sid = _cut(subscription_id, 64)
    uid = _cut(user_id, 64)
    if not sid or not uid:
        return {"ok": False, "message": "缺少 subscription_id 或 user_id"}
    now = datetime.now()
    with SessionLocal() as db:
        row = db.query(PushSubscription).filter(
            PushSubscription.subscription_id == sid).first()
        if row:
            row.user_id = uid
            row.platform = _cut(platform or "web", 20)
            row.device_type = _cut(device_type, 20)
            row.browser = _cut(browser, 40)
            row.user_agent = _cut(user_agent, 255)
            row.opted_in = bool(opted_in)
            row.last_seen_at = now
            row.revoked_at = None      # 重新授权时复活
        else:
            db.add(PushSubscription(
                user_id=uid, subscription_id=sid, platform=_cut(platform or "web", 20),
                device_type=_cut(device_type, 20), browser=_cut(browser, 40),
                user_agent=_cut(user_agent, 255), opted_in=bool(opted_in),
                created_at=now, updated_at=now, last_seen_at=now))
        db.commit()
    return {"ok": True, "subscription_id": sid}


def revoke_subscription(user_id: str, subscription_id: str = "") -> dict:
    """解绑订阅（登出时调用；不传 subscription_id 则解绑该用户全部设备）"""
    from app.database import SessionLocal
    from app.models.push import PushSubscription

    now = datetime.now()
    with SessionLocal() as db:
        q = db.query(PushSubscription).filter(
            PushSubscription.user_id == _cut(user_id, 64),
            PushSubscription.revoked_at.is_(None))
        if subscription_id:
            q = q.filter(PushSubscription.subscription_id == _cut(subscription_id, 64))
        rows = q.all()
        for r in rows:
            r.revoked_at = now
            r.opted_in = False
        db.commit()
    return {"ok": True, "revoked": len(rows)}


def subscription_stats() -> dict:
    """订阅概况（后台展示）：有效订阅数 / 涉及用户数 / 各平台分布"""
    from sqlalchemy import func

    from app.database import SessionLocal
    from app.models.push import PushSubscription

    with SessionLocal() as db:
        active = db.query(PushSubscription).filter(PushSubscription.revoked_at.is_(None),
                                                   PushSubscription.opted_in.is_(True))
        total = active.count()
        users = active.with_entities(func.count(func.distinct(PushSubscription.user_id))).scalar()
        by_platform = dict(
            db.query(PushSubscription.platform, func.count(PushSubscription.id))
            .filter(PushSubscription.revoked_at.is_(None))
            .group_by(PushSubscription.platform).all() or [])
    return {"subscriptions": total or 0, "users": users or 0, "by_platform": by_platform}


# ─────────────────────────── 偏好读写 ───────────────────────────

def get_prefs(user_id: str) -> dict:
    """读用户推送偏好（无记录返回全开默认值，不写库）"""
    from app.database import SessionLocal
    from app.models.push import PushPref

    with SessionLocal() as db:
        row = db.query(PushPref).filter(PushPref.user_id == _cut(user_id, 64)).first()
        if not row:
            return {"enable_study": True, "enable_im": True, "enable_announce": True,
                    "enable_exam": True, "quiet_start": "", "quiet_end": ""}
        return {"enable_study": bool(row.enable_study), "enable_im": bool(row.enable_im),
                "enable_announce": bool(row.enable_announce),
                "enable_exam": bool(row.enable_exam),
                "quiet_start": row.quiet_start or "", "quiet_end": row.quiet_end or ""}


def save_prefs(user_id: str, **fields) -> dict:
    """保存偏好（只更新传入的字段；缺行则新建）"""
    from app.database import SessionLocal
    from app.models.push import PushPref

    uid = _cut(user_id, 64)
    allowed = ("enable_study", "enable_im", "enable_announce", "enable_exam",
               "quiet_start", "quiet_end")
    with SessionLocal() as db:
        row = db.query(PushPref).filter(PushPref.user_id == uid).first()
        if not row:
            row = PushPref(user_id=uid)
            db.add(row)
        for k in allowed:
            if k in fields and fields[k] is not None:
                if k.startswith("quiet_"):
                    # 只接受合法 HH:MM，非法值视为「不启用」，避免脏数据让免打扰永远生效
                    v = str(fields[k]).strip()
                    setattr(row, k, v if _parse_hhmm(v) else "")
                else:
                    setattr(row, k, bool(fields[k]))
        row.updated_at = datetime.now()
        db.commit()
        return {"enable_study": bool(row.enable_study), "enable_im": bool(row.enable_im),
                "enable_announce": bool(row.enable_announce),
                "enable_exam": bool(row.enable_exam),
                "quiet_start": row.quiet_start or "", "quiet_end": row.quiet_end or ""}


def recent_logs(limit: int = 50, event: str = "") -> list:
    """最近发送记录（后台审计用）"""
    from app.database import SessionLocal
    from app.models.push import PushLog

    with SessionLocal() as db:
        q = db.query(PushLog)
        if event:
            q = q.filter(PushLog.event == event)
        rows = q.order_by(PushLog.id.desc()).limit(max(1, min(int(limit or 50), 200))).all()
        return [{
            "id": r.id, "user_id": r.user_id, "event": r.event,
            "event_label": event_label(r.event), "title": r.title, "body": r.body,
            "recipients": r.recipients or 0, "ok": bool(r.ok),
            "http_status": r.http_status or 0, "error": r.error or "",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        } for r in rows]
