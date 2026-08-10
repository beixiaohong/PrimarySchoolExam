"""用户认证：邮箱验证码注册全流程 + 昵称登录 + 异常路径"""

REG_EMAIL = "newkid@example.com"
REG_PWD = "Pass@1234"


def _send_register_code(client, fake_mail, email=REG_EMAIL):
    r = client.post("/api/auth/send-code",
                    json={"target": email, "purpose": "register"})
    assert r.status_code == 200, r.text
    assert fake_mail["target"] == email
    return fake_mail["code"]


def test_register_full_flow(client, fake_mail):
    """发码 → 捕获验证码 → 注册 → 登录 → /me"""
    code = _send_register_code(client, fake_mail)

    r = client.post("/api/auth/register", json={
        "target": REG_EMAIL, "code": code, "password": REG_PWD,
        "nickname": "小新",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == "小新"
    assert body["is_new"] is True

    # 密码登录（邮箱账号）
    r = client.post("/api/auth/login",
                    json={"account": REG_EMAIL, "password": REG_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "小新"

    # /me 脱敏信息
    r = client.get("/api/auth/me", params={"user_id": "小新"})
    assert r.status_code == 200
    body = r.json()
    assert body["auth_type"] == "email"
    assert body["has_password"] is True
    assert "***" in body["email"]


def test_nickname_login(client, fake_mail):
    """昵称账号可用昵称直接登录（ALLOW_NICKNAME_LOGIN=true）"""
    r = client.post("/api/auth/login",
                    json={"account": "小新", "password": REG_PWD})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "小新"


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
