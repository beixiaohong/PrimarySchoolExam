"""S1 基础能力测试：可观测性（request-id / 统一错误信封）+ RBAC 权限依赖。

运行依赖：MySQL 测试库（conftest 自动建 <DB_NAME>_test，与生产库隔离）。
不依赖外部 AI/邮件服务（conftest 已打桩）。
"""
import secrets
from datetime import datetime, timedelta

from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS, has_perm
from app.database import SessionLocal
from app.models.admin import Admin


def test_rbac_matrix():
    """权限矩阵：super 全有；admin 运营子集且无财务/订单/权限管理；ops 仅只读。"""
    all_codes = [p["code"] for p in PERMISSIONS]
    for code in all_codes:
        assert has_perm("super", code) is True
    assert has_perm("admin", "benefit:grant_manual") is True
    assert has_perm("admin", "finance:refund") is False
    assert has_perm("admin", "order:confirm_payment") is False
    assert has_perm("admin", "rbac:manage") is False
    assert has_perm("ops", "dashboard:view") is True
    assert has_perm("ops", "benefit:grant_manual") is False
    # 未知角色无任何权限
    assert has_perm("ghost", "dashboard:view") is False
    # 角色映射覆盖完整：super 映射数 = 目录总数
    assert len(ROLE_PERMISSIONS["super"]) == len(all_codes)


def test_request_id_header(client):
    """可观测性：每个响应都带 X-Request-ID。"""
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) >= 16


def _make_admin(role: str):
    db = SessionLocal()
    tok = secrets.token_urlsafe(16)
    db.add(Admin(
        username=f"{role}_{secrets.token_hex(4)}", password_hash="x", role=role,
        token=tok, token_expires_at=datetime.now() + timedelta(hours=1),
    ))
    db.commit()
    db.close()
    return tok


def test_rbac_enforcement(client, monkeypatch):
    """RBAC_STRICT=true 时：ops 无 benefit:grant_manual → 403；super → 200。"""
    monkeypatch.setattr("app.core.permissions.RBAC_STRICT", True)
    ops_tok = _make_admin("ops")
    sup_tok = _make_admin("super")

    body = {"user_id": "test_auth_uid", "asset": "coin", "amount": 10, "reason": "t"}
    # ops 缺权限 → 403
    r1 = client.post("/api/admin/assets/adjust", json=body,
                     headers={"Authorization": f"Bearer {ops_tok}"})
    assert r1.status_code == 403
    # super 拥有全部 → 200
    r2 = client.post("/api/admin/assets/adjust", json=body,
                     headers={"Authorization": f"Bearer {sup_tok}"})
    assert r2.status_code == 200


def test_validation_envelope(client, monkeypatch):
    """统一错误信封：校验失败返回 {code:422, request_id}。"""
    monkeypatch.setattr("app.core.permissions.RBAC_STRICT", True)
    sup_tok = _make_admin("super")
    # 缺必填字段（asset/amount/reason）→ 422
    r = client.post("/api/admin/assets/adjust", json={"user_id": "test_auth_uid"},
                    headers={"Authorization": f"Bearer {sup_tok}"})
    assert r.status_code == 422
    payload = r.json()
    assert payload["code"] == 422
    assert "request_id" in payload
