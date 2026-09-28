"""消息推送（OneSignal Web Push）测试

钉死七件事：
① 未配置时整体降级：`push_configured()` 为 False、`/api/push/config` 的 enabled=False，
   发送函数直接返回 not_configured **不发任何 HTTP**（用户没配密钥不该有出网请求）；
② 配置读取走 sysconfig（后台可在线覆盖 .env），配置齐全即可用；
③ 纯函数口径：`abs_url` 补绝对地址、`in_quiet_hours` 跨零点/未启用、`pref_allows` 场景开关；
④ 订阅生命周期（集成）：上报 upsert 幂等（同一 subscription_id 换账号会改写归属）、
   解绑后不再计入有效设备；
⑤ 发送链路（打桩 OneSignal REST）：请求体用 `include_aliases.external_id`（= 本系统 user_id）、
   `target_channel=push`、带 Authorization 头；发送结果落 push_logs；
⑥ 防打扰三闸：dedup_key 去重、场景偏好关闭、免打扰时段、每人每日上限；
⑦ Service Worker 由后端根路径托管（nginx 全量反代下 dist 静态目录不暴露，
   缺这条路由 OneSignal 初始化必然失败），且带 no-store 与 Service-Worker-Allowed。

conftest 强制 MySQL 测试库、不做事回滚 → 每用例专属 user_id + finally 清理自身数据。
"""
import json
from datetime import datetime

import pytest

from app.database import SessionLocal
from app.models.push import PushLog, PushPref, PushSubscription

UID = "push_test_uid"
UID2 = "push_test_uid2"
SID = "push-test-sub-0001"


# ── 夹具 ──

@pytest.fixture()
def push_on(monkeypatch):
    """打开推送通道配置（打桩 sysconfig，避免依赖 .env 与后台真实配置）"""
    import app.domains.platform.services.push as push

    cfg = {
        "ONESIGNAL_APP_ID": "test-app-id",
        "ONESIGNAL_REST_API_KEY": "test-rest-key",
        "ONESIGNAL_SAFARI_WEB_ID": "web.test.safari",
        "PUSH_ENABLED": "true",
        "SITE_URL": "https://example.com",
    }
    monkeypatch.setattr(push.sysconfig, "get",
                        lambda key, default="": cfg.get(key, default))
    return cfg


@pytest.fixture()
def push_off(monkeypatch):
    """通道未配置（APP_ID / REST_KEY 均为空）"""
    import app.domains.platform.services.push as push

    monkeypatch.setattr(push.sysconfig, "get", lambda key, default="": default)


@pytest.fixture()
def fake_push(monkeypatch):
    """打桩 OneSignal REST API：记录请求并返回可控响应。

    返回 (calls, state)：calls 是请求列表；state 可改 id/recipients/ok 模拟各种返回。
    """
    import app.domains.platform.services.push as push

    calls = []
    state = {"id": "os-msg-1", "recipients": 3, "ok": True}

    class _Resp:
        def __init__(self, body, status):
            self.status_code = status
            self._body = body
            self.text = json.dumps(body)

        def json(self):
            return self._body

    class _FakeRequests:
        @staticmethod
        def post(url, json=None, headers=None, timeout=None):
            calls.append({"url": url, "json": json, "headers": headers})
            if not state["ok"]:
                return _Resp({"errors": ["invalid api key"]}, 401)
            body = {"recipients": state["recipients"]}
            if state["id"]:
                body["id"] = state["id"]
            return _Resp(body, 200)

    monkeypatch.setattr(push, "requests", _FakeRequests)
    return calls, state


def _cleanup(*uids):
    s = SessionLocal()
    try:
        for uid in uids:
            s.query(PushSubscription).filter(PushSubscription.user_id == uid).delete()
            s.query(PushPref).filter(PushPref.user_id == uid).delete()
            s.query(PushLog).filter(PushLog.user_id == uid).delete()
        s.query(PushSubscription).filter(
            PushSubscription.subscription_id.like("push-test-%")).delete()
        s.query(PushLog).filter(PushLog.dedup_key.like("push-test-%")).delete()
        s.commit()
    finally:
        s.close()


# ── ① 未配置降级 ──

def test_not_configured_degrades(push_off, client):
    """未填密钥：判定为不可用、配置端点如实回 false，且**不产生任何出网请求**"""
    import app.domains.platform.services.push as push

    assert push.push_configured() is False
    assert push.push_sdk_config()["enabled"] is False
    assert push.push_sdk_config()["app_id"] == ""

    r = client.get("/api/push/config")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["app_id"] == ""
    # 偏好仍要返回（前端据它渲染默认全开），避免「整块消失」
    assert body["prefs"]["enable_study"] is True


def test_send_skips_without_config(push_off, fake_push):
    """未配置时发送函数直接返回，不发 HTTP、不写日志"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    res = push.send_to_users([UID], "标题", "正文", event=push.EVENT_STUDY)
    assert res["ok"] is False and res["reason"] == "not_configured"
    assert calls == []
    s = SessionLocal()
    try:
        assert s.query(PushLog).filter(PushLog.user_id == UID).count() == 0
    finally:
        s.close()


def test_configured(monkeypatch, push_on):
    """配置齐全即视为可用（PUSH_ENABLED=false 则一键停推）"""
    import app.domains.platform.services.push as push

    assert push.push_configured() is True
    assert push.push_sdk_config()["app_id"] == "test-app-id"
    assert push.push_sdk_config()["safari_web_id"] == "web.test.safari"

    monkeypatch.setattr(push.sysconfig, "get",
                        lambda key, default="": "false" if key == "PUSH_ENABLED"
                        else {"ONESIGNAL_APP_ID": "a", "ONESIGNAL_REST_API_KEY": "b"}.get(key, default))
    assert push.push_configured() is False


# ── ③ 纯函数 ──

@pytest.mark.parametrize("path,expected", [
    ("", ""),
    ("/#/home", "https://example.com/#/home"),
    ("home", "https://example.com/home"),
    ("https://other.com/x", "https://other.com/x"),
])
def test_abs_url(push_on, path, expected):
    import app.domains.platform.services.push as push

    assert push.abs_url(path) == expected


class _P:
    """轻量偏好替身（只带 in_quiet_hours/pref_allows 需要的属性）"""

    def __init__(self, start="", end="", **flags):
        self.quiet_start = start
        self.quiet_end = end
        for k in ("enable_study", "enable_im", "enable_announce", "enable_exam"):
            setattr(self, k, flags.get(k, True))


@pytest.mark.parametrize("start,end,hour,expected", [
    ("22:00", "07:00", 23, True),     # 跨零点：区间内
    ("22:00", "07:00", 3, True),      # 跨零点：凌晨仍在区间
    ("22:00", "07:00", 12, False),    # 跨零点：白天不在区间
    ("13:00", "14:00", 13, True),     # 普通区间
    ("13:00", "14:00", 15, False),
    ("", "", 23, False),              # 未启用
    ("09:00", "09:00", 9, False),     # 起止相同视为未启用（否则全天静音）
    ("25:00", "07:00", 3, False),     # 非法值不生效
])
def test_in_quiet_hours(start, end, hour, expected):
    import app.domains.platform.services.push as push

    assert push.in_quiet_hours(_P(start, end), datetime(2026, 9, 28, hour, 30)) is expected


def test_pref_allows():
    """场景开关：关闭的类别不放行；无偏好行（None）按全开"""
    import app.domains.platform.services.push as push

    assert push.pref_allows(None, push.EVENT_STUDY) is True
    assert push.pref_allows(_P(enable_study=False), push.EVENT_STUDY) is False
    assert push.pref_allows(_P(enable_study=False), push.EVENT_IM) is True
    # test/broadcast 未登记偏好字段 → 恒放行
    assert push.pref_allows(_P(enable_study=False), push.EVENT_TEST) is True


# ── ④ 订阅生命周期（集成） ──

def test_subscribe_upsert_and_revoke(client):
    """上报幂等（同一 subscription_id 换账号改写归属）；解绑后不再计入有效设备"""
    try:
        r = client.post("/api/push/subscribe", json={
            "user_id": UID, "subscription_id": SID, "platform": "web",
            "device_type": "Desktop", "browser": "Chrome", "user_agent": "UA/1.0"})
        assert r.status_code == 200 and r.json()["ok"] is True

        r = client.get("/api/push/status?user_id=%s" % UID)
        assert r.json()["subscribed_devices"] == 1

        # 同一浏览器换账号登录：归属改写而不是新增一行
        r = client.post("/api/push/subscribe", json={
            "user_id": UID2, "subscription_id": SID, "platform": "web"})
        assert r.status_code == 200
        s = SessionLocal()
        try:
            rows = s.query(PushSubscription).filter(
                PushSubscription.subscription_id == SID).all()
            assert len(rows) == 1 and rows[0].user_id == UID2
        finally:
            s.close()

        # 解绑：设备数归零，且再次上报能复活
        r = client.post("/api/push/unsubscribe", json={"user_id": UID2,
                                                       "subscription_id": SID})
        assert r.json()["revoked"] == 1
        assert client.get("/api/push/status?user_id=%s" % UID2).json()["subscribed_devices"] == 0
    finally:
        _cleanup(UID, UID2)


def test_prefs_roundtrip(client):
    """偏好读写：只改传入字段，非法免打扰值归一为空（不启用）"""
    try:
        r = client.put("/api/push/prefs", json={"user_id": UID, "enable_im": False})
        assert r.status_code == 200
        assert r.json()["enable_im"] is False
        assert r.json()["enable_study"] is True          # 未传字段不动

        r = client.put("/api/push/prefs", json={"user_id": UID,
                                                "quiet_start": "21:30",
                                                "quiet_end": "07:00"})
        assert r.json()["quiet_start"] == "21:30"

        r = client.put("/api/push/prefs", json={"user_id": UID,
                                                "quiet_start": "不是时间"})
        assert r.json()["quiet_start"] == ""             # 非法值 → 不启用，不写脏数据

        r = client.get("/api/push/prefs?user_id=%s" % UID)
        assert r.json()["enable_im"] is False
    finally:
        _cleanup(UID)


# ── ⑤ 发送链路 ──

def test_send_uses_external_id_and_logs(push_on, fake_push):
    """请求体形状：external_id 定向 + push 通道 + Key 鉴权头；成功结果落日志"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    res = push.send_to_users([UID], "作业提醒", "还有 2 项任务没完成",
                             url="/#/home", event=push.EVENT_STUDY,
                             dedup_key="push-test-a")
    assert res["ok"] is True and res["sent"] == 1
    assert len(calls) == 1
    body = calls[0]["json"]
    assert body["include_aliases"]["external_id"] == [UID]
    assert body["target_channel"] == "push"
    assert body["app_id"] == "test-app-id"
    assert body["contents"]["zh-Hans"] == "还有 2 项任务没完成"
    assert body["url"] == "https://example.com/#/home"
    assert calls[0]["headers"]["Authorization"] == "Key test-rest-key"

    s = SessionLocal()
    try:
        log = s.query(PushLog).filter(PushLog.dedup_key == "push-test-a").first()
        assert log is not None and log.ok is True and log.event == "study"
    finally:
        s.close()
        _cleanup(UID)


def test_send_dedup_key_blocks_repeat(push_on, fake_push):
    """同一 dedup_key 第二次直接跳过（定时任务重跑/接口重试不会重复打扰）"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    assert push.send_to_users([UID], "T", "B", event=push.EVENT_STUDY,
                              dedup_key="push-test-dup")["ok"] is True
    res = push.send_to_users([UID], "T", "B", event=push.EVENT_STUDY,
                             dedup_key="push-test-dup")
    assert res["ok"] is False and res["reason"] == "duplicate"
    assert len(calls) == 1          # 只发过一次
    _cleanup(UID)


def test_send_respects_pref_off(push_on, fake_push):
    """场景偏好关闭 → 不发送（不放行到 HTTP）"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    s = SessionLocal()
    try:
        s.add(PushPref(user_id=UID, enable_study=False))
        s.commit()
    finally:
        s.close()

    res = push.send_to_users([UID], "T", "B", event=push.EVENT_STUDY)
    assert res["ok"] is False and res["reason"] == "all_filtered"
    assert calls == []
    _cleanup(UID)


def test_send_respects_quiet_hours(push_on, fake_push):
    """免打扰时段内不发送（这里用全天区间，避免依赖执行时刻）"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    s = SessionLocal()
    try:
        s.add(PushPref(user_id=UID, quiet_start="00:00", quiet_end="23:59"))
        s.commit()
    finally:
        s.close()

    res = push.send_to_users([UID], "T", "B", event=push.EVENT_STUDY)
    assert res["ok"] is False and res["reason"] == "quiet_hours"
    assert calls == []
    _cleanup(UID)


def test_send_daily_cap(push_on, fake_push):
    """自动事件达到每人每日上限后不再发送；运营类事件不受限"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    s = SessionLocal()
    try:
        for _ in range(push.DAILY_CAP):
            s.add(PushLog(user_id=UID, event=push.EVENT_STUDY, title="t", body="b",
                          ok=True, created_at=datetime.now()))
        s.commit()
    finally:
        s.close()

    assert push.send_to_users([UID], "T", "B", event=push.EVENT_STUDY)["reason"] == "all_filtered"
    assert calls == []
    # 公告类不占额度（否则一条公告就把用户的额度吃光，后续真实提醒全被吞掉）
    assert push.send_to_users([UID], "T", "B", event=push.EVENT_ANNOUNCE)["ok"] is True
    assert len(calls) == 1
    _cleanup(UID)


def test_send_200_without_id_means_no_subscription(push_on, fake_push):
    """OneSignal 返回 200 但没有 id：说明靶向受众里没有有效订阅，必须如实标注"""
    import app.domains.platform.services.push as push

    calls, state = fake_push
    state["id"] = None
    state["recipients"] = 0
    res = push.send_to_users([UID], "T", "B", event=push.EVENT_TEST)
    assert res["ok"] is False and res["sent"] == 0
    assert "no_subscription" in (res.get("message") or "")
    _cleanup(UID)


def test_send_http_error_recorded(push_on, fake_push):
    """OneSignal 报错：ok=False 且错误落日志（便于后台排查密钥/AppID 不匹配）

    失败时写的是**汇总行**（user_id 为空）且不带 dedup_key —— 不带去重键是为了让
    重跑能补发；汇总而非逐用户是因为整批共用一次 HTTP 结果。
    """
    import app.domains.platform.services.push as push

    calls, state = fake_push
    state["ok"] = False
    res = push.send_to_users([UID], "T", "B", event=push.EVENT_TEST)
    assert res["ok"] is False and res["sent"] == 0
    s = SessionLocal()
    try:
        log = (s.query(PushLog)
               .filter(PushLog.event == push.EVENT_TEST, PushLog.ok.is_(False))
               .order_by(PushLog.id.desc()).first())
        assert log is not None
        assert "invalid api key" in (log.error or "")
        assert log.dedup_key is None and log.http_status == 401
    finally:
        s.close()
        _cleanup(UID)


def test_send_per_user_dedup(push_on, fake_push):
    """逐人去重：同一模板键第二次调用整批跳过，成功后为每人写下去重记录"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    tmpl = "push-test-{uid}:2026-09-28"
    res = push.send_per_user_dedup([UID, UID2], "新消息", "你好",
                                   event=push.EVENT_IM, key_template=tmpl)
    assert res["ok"] is True and res["sent"] == 2
    assert len(calls) == 1                       # 一批只发一个 HTTP 请求
    assert sorted(calls[0]["json"]["include_aliases"]["external_id"]) == sorted([UID, UID2])

    res2 = push.send_per_user_dedup([UID, UID2], "新消息", "你好",
                                    event=push.EVENT_IM, key_template=tmpl)
    assert res2["ok"] is False and res2["reason"] == "duplicate"
    assert len(calls) == 1
    _cleanup(UID, UID2)


def test_broadcast_uses_segment(push_on, fake_push):
    """全体广播走分段（不枚举用户）；返回触达订阅数"""
    import app.domains.platform.services.push as push

    calls, _ = fake_push
    res = push.send_to_all("全校通知", "明天放假", event=push.EVENT_ANNOUNCE)
    assert res["ok"] is True and res["recipients"] == 3
    body = calls[0]["json"]
    assert body["included_segments"] == ["Subscribed Users"]
    assert "include_aliases" not in body
    _cleanup(UID)


# ── 端点 ──

def test_self_test_endpoint(push_on, fake_push, client):
    """自助测试推送：通道就绪时返回成功提示"""
    calls, _ = fake_push
    r = client.post("/api/push/test", json={"user_id": UID})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert len(calls) == 1
    _cleanup(UID)


def test_self_test_endpoint_reports_reason(push_off, client):
    """未配置时给出可操作的中文原因（而不是干瘪的失败）"""
    r = client.post("/api/push/test", json={"user_id": UID})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "未配置" in r.json()["message"]


# ── ⑦ Service Worker 托管 ──

def test_service_worker_route(client):
    """根路径托管 SW：MIME 正确、scope 允许全站、禁缓存（否则 SDK 升级后老客户端失效）"""
    r = client.get("/OneSignalSDKWorker.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert r.headers.get("service-worker-allowed") == "/"
    assert "no-store" in r.headers.get("cache-control", "")
    assert "OneSignalSDK.sw.js" in r.text


def test_service_worker_accepts_head(client):
    """HEAD 也要通（回归防线）：运维验 SW 最顺手的是 `curl -I`，那发的是 HEAD。

    `@app.get` 只注册 GET、Starlette 不会自动补 HEAD —— 历史上这里返回 405，
    会被误判成「路由没生效/部署失败」，白排查一轮。响应体由协议层丢弃即可。
    """
    r = client.head("/OneSignalSDKWorker.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert r.headers.get("service-worker-allowed") == "/"
    assert "no-store" in r.headers.get("cache-control", "")


# ── 后台 ──

def test_admin_push_status_and_send(client, admin_headers, push_on, fake_push):
    """后台：状态可见、群发走分段、日志可查"""
    calls, _ = fake_push
    r = client.get("/api/admin/push/status", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True and body["configured"]["app_id"] is True

    r = client.post("/api/admin/push/send", headers=admin_headers, json={
        "title": "系统维护", "body": "今晚 23 点维护", "url": "/#/home",
        "target": "all", "event": "announce"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert calls[0]["json"]["included_segments"] == ["Subscribed Users"]

    r = client.get("/api/admin/push/logs", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1


def test_admin_push_send_requires_config(client, admin_headers, push_off):
    """后台在未配置时发送：明确 400 提示去配密钥，而不是静默成功"""
    r = client.post("/api/admin/push/send", headers=admin_headers, json={
        "title": "T", "body": "B", "target": "all"})
    assert r.status_code == 400
    assert "未配置" in r.json()["message"]


def test_admin_push_send_to_user(client, admin_headers, push_on, fake_push):
    """指定用户定向：external_id 只含该用户；无接收者时 400"""
    calls, _ = fake_push
    r = client.post("/api/admin/push/send", headers=admin_headers, json={
        "title": "T", "body": "B", "target": "user", "user_ids": [UID]})
    assert r.status_code == 200
    assert calls[0]["json"]["include_aliases"]["external_id"] == [UID]

    r = client.post("/api/admin/push/send", headers=admin_headers, json={
        "title": "T", "body": "B", "target": "user", "user_ids": []})
    assert r.status_code == 400
    _cleanup(UID)
