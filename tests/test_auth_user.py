"""用户认证：邮箱验证码注册全流程 + 昵称登录关闭回归 + 异常路径"""

REG_EMAIL = "newkid@example.com"
REG_PWD = "Pass@1234"


def _send_register_code(client, fake_mail, email=REG_EMAIL):
    r = client.post("/api/auth/send-code",
                    json={"target": email, "purpose": "register"})
    assert r.status_code == 200, r.text
    assert fake_mail["target"] == email
    return fake_mail["code"]


def test_register_full_flow(client, fake_mail):
    """发码 → 捕获验证码 → 注册（生成字母数字 user_id）→ 登录 → /me"""
    code = _send_register_code(client, fake_mail)

    r = client.post("/api/auth/register", json={
        "target": REG_EMAIL, "code": code, "password": REG_PWD,
        "nickname": "小新",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    uid = body["user_id"]
    # 新注册账号 user_id 由服务端生成随机「u 前缀 + 字母数字」，与昵称彻底解耦
    assert uid.startswith("u") and uid.isalnum(), f"user_id 应为字母数字串: {uid!r}"
    assert uid != "小新", "user_id 不应等于昵称"
    assert body["nickname"] == "小新"
    assert body["is_new"] is True

    # 密码登录（邮箱账号），返回含登录 token
    r = client.post("/api/auth/login",
                    json={"account": REG_EMAIL, "password": REG_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == uid
    token = r.json()["token"]
    assert token

    # /me 脱敏信息（需携带登录 token；不再接受 user_id 参数）
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == uid
    assert body["auth_type"] == "email"
    assert body["has_password"] is True
    assert "***" in body["email"]


def test_nickname_login_rejected(client):
    """昵称登录已关闭：仅邮箱+密码可登录，纯昵称账号直接 400"""
    r = client.post("/api/auth/login",
                    json={"account": "小新", "password": REG_PWD})
    assert r.status_code == 400
    assert "邮箱" in r.json()["detail"]


def test_register_wrong_code(client, fake_mail):
    """错误验证码被拒绝"""
    email = "wrongcode@example.com"
    _send_register_code(client, fake_mail, email)
    r = client.post("/api/auth/register", json={
        "target": email, "code": "000000", "password": REG_PWD,
    })
    # 极低概率撞对真实码，若撞对则跳过
    if r.status_code == 200:
        return
    assert r.status_code == 400
    assert "验证码" in r.json()["detail"]


def test_register_duplicate_rejected(client, fake_mail):
    """已注册邮箱再次发注册码被拒"""
    r = client.post("/api/auth/send-code",
                    json={"target": REG_EMAIL, "purpose": "register"})
    assert r.status_code == 400
    assert "已注册" in r.json()["detail"]


def test_send_code_rate_limit(client, fake_mail):
    """同一目标 60 秒内重复发码被频控"""
    email = "ratelimit@example.com"
    r1 = client.post("/api/auth/send-code",
                     json={"target": email, "purpose": "register"})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/send-code",
                     json={"target": email, "purpose": "register"})
    assert r2.status_code == 429


def test_login_wrong_password(client, fake_mail):
    r = client.post("/api/auth/login",
                    json={"account": REG_EMAIL, "password": "WrongPwd1"})
    assert r.status_code == 403


def test_business_endpoint_requires_login():
    """业务接口未携带登录 token 必须 401（安全回归）"""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        # 不带 Authorization 头直接访问业务接口
        r = c.get("/api/user/info", params={"user_id": "test_auth_uid"})
        assert r.status_code == 401


def test_docs_disabled_by_default():
    """生产默认关闭 Swagger/ReDoc/OpenAPI 文档（安全回归）"""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/redoc").status_code == 404
        assert c.get("/openapi.json").status_code == 404


def test_strict_binding_blocks_other_user_id(client):
    """严格账号绑定（安全回归）：用「本人 token」+「他人 user_id」调业务接口必须 403。

    关键点：显式传入 test_auth_uid 的 token（本人），但请求 user_id 写成他人，
    以此证明 require_self 拒绝「token 账号 ≠ 请求 user_id」。
    注意不可依赖 AuthClient 的自动按请求 user_id 签 token（会误判为合法）。
    """
    token = client._mint_token("test_auth_uid")  # 本人 token
    r = client.get("/api/user/info",
                   headers={"Authorization": f"Bearer {token}"},
                   params={"user_id": "someone_else_xyz"})
    assert r.status_code == 403, r.text


def test_strict_binding_allows_self(client):
    """严格账号绑定（安全回归）：本人 token + 本人 user_id 调业务接口正常 200。

    AuthClient 会按请求 user_id 自动签匹配 token，等价于「本人调本人」。
    """
    r = client.get("/api/user/info", params={"user_id": "test_auth_uid"})
    assert r.status_code == 200, r.text


def test_strict_binding_blocks_other_user_id_body(client):
    """严格账号绑定（POST/JSON body 形态）：本人 token + 他人 user_id 必须 403。"""
    token = client._mint_token("test_auth_uid")  # 本人 token
    r = client.post("/api/parent/message",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"user_id": "someone_else_xyz", "content": "测试留言"})
    assert r.status_code == 403, r.text


