"""P0-1 RBAC 收口回归：IM / 账本 / 公告 后台写接口权限闸门。

校验：
1. 权限矩阵：admin 角色拥有 im:manage / ledger:manage / announcement:manage；
   ops 角色不拥有（仍只读）。
2. 接口闸门：RBAC_STRICT=true 下，未授权角色（ops）调高危写接口 → 403；
   授权角色（admin）通过闸门（资源不存在 → 404，证明非 403 被拦）。

运行依赖：MySQL 测试库（conftest 自动建 <DB_NAME>_test，与生产库隔离；
迁移 062 在 TestClient 启动时落库，确保新权限点已种子）。
"""
import secrets
from datetime import datetime, timedelta

from app.core.permissions import has_perm
from app.database import SessionLocal
from app.models.admin import Admin


def _make_admin(role: str) -> str:
    db = SessionLocal()
    tok = secrets.token_urlsafe(16)
    db.add(Admin(
        username=f"{role}_{secrets.token_hex(4)}", password_hash="x", role=role,
        token=tok, token_expires_at=datetime.now() + timedelta(hours=1),
    ))
    db.commit()
    db.close()
    return tok


def test_rbac_freeze_admin_role_mapping():
    """权限矩阵：admin 含三个新权限点；ops 不含（保持只读）。"""
    assert has_perm("admin", "im:manage") is True
    assert has_perm("admin", "ledger:manage") is True
    assert has_perm("admin", "announcement:manage") is True
    assert has_perm("super", "im:manage") is True
    # ops 仍为只读，不能写 IM / 账本 / 公告
    assert has_perm("ops", "im:manage") is False
    assert has_perm("ops", "ledger:manage") is False
    assert has_perm("ops", "announcement:manage") is False


def test_im_write_requires_perm(client, monkeypatch):
    """RBAC_STRICT=true：ops 写 IM → 403；admin 通过闸门 → 404（资源不存在）。"""
    monkeypatch.setattr("app.core.permissions.RBAC_STRICT", True)
    admin_tok = _make_admin("admin")
    ops_tok = _make_admin("ops")
    h_admin = {"Authorization": f"Bearer {admin_tok}"}
    h_ops = {"Authorization": f"Bearer {ops_tok}"}

    r1 = client.delete("/api/admin/im/chats/999", headers=h_ops)
    assert r1.status_code == 403
    r2 = client.delete("/api/admin/im/chats/999", headers=h_admin)
    assert r2.status_code == 404  # 通过权限闸门，仅因资源不存在

    r3 = client.delete("/api/admin/im/sensitive-words/999", headers=h_ops)
    assert r3.status_code == 403
    r4 = client.delete("/api/admin/im/sensitive-words/999", headers=h_admin)
    assert r4.status_code == 404


def test_ledger_write_requires_perm(client, monkeypatch):
    """RBAC_STRICT=true：ops 写账本 → 403；admin 通过闸门 → 404。"""
    monkeypatch.setattr("app.core.permissions.RBAC_STRICT", True)
    admin_tok = _make_admin("admin")
    ops_tok = _make_admin("ops")
    h_admin = {"Authorization": f"Bearer {admin_tok}"}
    h_ops = {"Authorization": f"Bearer {ops_tok}"}

    r1 = client.delete("/api/admin/ledger/bills/999", headers=h_ops)
    assert r1.status_code == 403
    r2 = client.delete("/api/admin/ledger/bills/999", headers=h_admin)
    assert r2.status_code == 404

    r3 = client.delete("/api/admin/ledger/accounts/999", headers=h_ops)
    assert r3.status_code == 403
    r4 = client.delete("/api/admin/ledger/accounts/999", headers=h_admin)
    assert r4.status_code == 404


def test_announcement_write_requires_perm(client, monkeypatch):
    """RBAC_STRICT=true：ops 发/删公告 → 403；admin 通过闸门。"""
    monkeypatch.setattr("app.core.permissions.RBAC_STRICT", True)
    admin_tok = _make_admin("admin")
    ops_tok = _make_admin("ops")
    h_admin = {"Authorization": f"Bearer {admin_tok}"}
    h_ops = {"Authorization": f"Bearer {ops_tok}"}

    r1 = client.post("/api/admin/announcements",
                     json={"title": "t", "content": "c"}, headers=h_ops)
    assert r1.status_code == 403
    r2 = client.post("/api/admin/announcements",
                     json={"title": "t", "content": "c"}, headers=h_admin)
    # admin 通过闸门，资源写入成功（201）或业务校验后落库；非 403
    assert r2.status_code != 403

    r3 = client.delete("/api/admin/announcements/999", headers=h_ops)
    assert r3.status_code == 403
    r4 = client.delete("/api/admin/announcements/999", headers=h_admin)
    assert r4.status_code == 404  # 通过闸门，仅因资源不存在
