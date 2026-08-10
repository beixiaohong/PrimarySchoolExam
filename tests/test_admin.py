"""管理后台：默认管理员登录 + token 鉴权 + 基础管理接口"""

import pytest

ADMIN_USER = "admin"
ADMIN_PWD = "Admin@123"


@pytest.fixture(scope="module")
def admin_token(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_admin_login_wrong_password(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": "WrongPwd"})
    assert r.status_code == 403


def test_admin_login_success(client):
    r = client.post("/api/admin/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PWD})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["username"] == ADMIN_USER


def test_admin_me_requires_token(client, admin_token):
    # 无 token → 401
    r = client.get("/api/admin/me")
    assert r.status_code == 401
    # 伪 token → 401
    r = client.get("/api/admin/me",
                   headers={"Authorization": "Bearer fake-token"})
    assert r.status_code == 401
    # 真 token → 200
    r = client.get("/api/admin/me",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["username"] == ADMIN_USER


def test_admin_users_and_dashboard(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/admin/users", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] >= 0

    r = client.get("/api/admin/dashboard", headers=h)
    assert r.status_code == 200

    r = client.get("/api/admin/logs", headers=h)
    assert r.status_code == 200
