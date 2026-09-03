"""S1 剩余交付物测试：B3 指标落表 / B7 审计增强 / B8 RBAC 服务 / B9 后台接口。

运行依赖：MySQL 测试库（conftest 自动建 <DB_NAME>_test，与生产库隔离）。
不依赖外部 AI/邮件服务（conftest 已打桩）。
"""
import secrets
from datetime import datetime, timedelta

from app.core.metrics import record_metric
from app.core.permissions import PERMISSIONS
from app.database import SessionLocal
from app.domains.platform.services import rbac as rbac_svc
from app.models.admin import Admin, AdminOperationLog
from app.models.metrics import MetricDaily


def _make_admin(role: str):
    db = SessionLocal()
    tok = secrets.token_urlsafe(16)
    uname = f"{role}_{secrets.token_hex(4)}"
    db.add(Admin(
        username=uname, password_hash="x", role=role,
        token=tok, token_expires_at=datetime.now() + timedelta(hours=1),
    ))
    db.commit()
    db.close()
    return tok, uname


# ───────────────────────── B3：指标落表 ─────────────────────────
def test_metric_daily_upsert(client):
    """record_metric 按 stat_date+metric_name+dimension 幂等 upsert。"""
    db = SessionLocal()
    try:
        record_metric(db, "dau", 100, dimension="")
        db.commit()
        record_metric(db, "dau", 250, dimension="")  # 同键 → 更新
        db.commit()
        row = db.query(MetricDaily).filter_by(metric_name="dau", dimension="").one()
        assert float(row.value) == 250
        # 不同维度 → 新行
        record_metric(db, "dau", 42, dimension="grade_3")
        db.commit()
        assert db.query(MetricDaily).filter_by(metric_name="dau").count() == 2
    finally:
        db.query(MetricDaily).filter_by(metric_name="dau").delete()
        db.commit()
        db.close()


# ───────────────────────── B7：审计增强字段 ─────────────────────────
def test_audit_enriched_fields(client):
    """_audit 写入新字段（ip/ua/amount_fen/target_type/extra_json）。"""
    db = SessionLocal()
    tok, uname = _make_admin("super")
    try:
        admin = db.query(Admin).filter_by(username=uname).first()
        from app.routers.admin.common import _audit
        _audit(db, admin, action="test:enrich", target="u1", detail="x",
               ip="1.2.3.4", user_agent="ua/1.0", amount_fen=9900,
               target_type="user", extra_json='{"k":1}')
        log = db.query(AdminOperationLog).filter_by(action="test:enrich").one()
        assert log.ip == "1.2.3.4"
        assert log.user_agent == "ua/1.0"
        assert log.amount_fen == 9900
        assert log.target_type == "user"
        assert log.extra_json == '{"k":1}'
    finally:
        db.query(AdminOperationLog).filter_by(action="test:enrich").delete()
        db.commit()
        db.close()


# ───────────────────────── B8：RBAC 服务互斥校验 ─────────────────────────
def test_rbac_mutex_check():
    """BR-PERM-04：order:confirm_payment 与 payment_account:manage 互斥。"""
    assert rbac_svc.check_mutex(
        ["order:confirm_payment", "payment_account:manage"]) is not None
    assert rbac_svc.check_mutex(["order:confirm_payment", "content:manage"]) is None


def test_rbac_set_role_permissions_mutex_rejected(client):
    """整体设置角色权限集命中互斥对 → 服务抛 ValueError(ERR_MUTEX)。"""
    db = SessionLocal()
    try:
        import pytest
        with pytest.raises(ValueError) as ei:
            rbac_svc.set_role_permissions(
                db, "ops",
                ["dashboard:view", "order:confirm_payment", "payment_account:manage"])
        assert rbac_svc.ERR_MUTEX in str(ei.value)
    finally:
        db.close()


# ───────────────────────── B9：后台接口 ─────────────────────────
def test_rbac_roles_and_permissions_endpoints(client):
    """GET /rbac/roles 与 /rbac/permissions 返回结构正确。"""
    tok, _ = _make_admin("super")
    h = {"Authorization": f"Bearer {tok}"}
    r1 = client.get("/api/admin/rbac/roles", headers=h)
    assert r1.status_code == 200
    roles = r1.json()
    assert {g["role"] for g in roles} == {"super", "admin", "ops"}
    r2 = client.get("/api/admin/rbac/permissions", headers=h)
    assert r2.status_code == 200
    codes = {p["code"] for p in r2.json()}
    assert "rbac:manage" in codes and "benefit:grant_manual" in codes


def test_rbac_set_role_mutex_via_api(client):
    """PUT /rbac/roles/{role} 命中互斥 → 400。"""
    tok, _ = _make_admin("super")
    h = {"Authorization": f"Bearer {tok}"}
    body = {"permissions": ["dashboard:view", "order:confirm_payment",
                            "payment_account:manage"]}
    r = client.put("/api/admin/rbac/roles/ops", json=body, headers=h)
    assert r.status_code == 400
    # 统一错误信封：消息在 message 字段
    assert rbac_svc.ERR_MUTEX in r.json()["message"]


def test_rbac_assign_admin_role(client):
    """POST /rbac/admins/{id}/role 正确分配角色。"""
    tok, _ = _make_admin("super")
    _, target_uname = _make_admin("ops")
    db = SessionLocal()
    target = db.query(Admin).filter_by(username=target_uname).first()
    db.close()
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post(f"/api/admin/rbac/admins/{target.id}/role",
                    json={"role": "admin"}, headers=h)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_audit_logs_pagination_and_high_risk(client):
    """GET /audit/logs 分页；/audit/high-risk 过滤高危（金额或高危分组）。"""
    tok, uname = _make_admin("super")
    db = SessionLocal()
    marker = f"hr_{secrets.token_hex(3)}"
    try:
        admin = db.query(Admin).filter_by(username=uname).first()
        db.add(AdminOperationLog(admin=marker, action="benefit:grant_manual",
                                 target="u1", detail="x", target_type="asset",
                                 amount_fen=None))  # 高危分组 benefit
        db.add(AdminOperationLog(admin=marker, action="content:manage",
                                 target="c1", detail="x", target_type="config",
                                 amount_fen=None))  # 非高危
        db.add(AdminOperationLog(admin=marker, action="order:refund",
                                 target="o1", detail="x", amount_fen=5000,
                                 target_type="order"))  # 金额非空 → 高危
        db.commit()

        h = {"Authorization": f"Bearer {tok}"}
        r = client.get(f"/api/admin/audit/logs?admin_name={marker}&page=1&page_size=10",
                       headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

        r2 = client.get(f"/api/admin/audit/high-risk", headers=h)
        assert r2.status_code == 200
        hr = r2.json()
        # 高危：benefit:grant_manual（分组命中）+ amount_fen 非空（order:refund）
        # 至少含本用例插入的 2 条（库内可能另有历史高危日志，故用子集断言）
        assert hr["total"] >= 2
        actions = {it["action"] for it in hr["items"]}
        assert "benefit:grant_manual" in actions and "order:refund" in actions
    finally:
        db.query(AdminOperationLog).filter_by(admin=marker).delete()
        db.commit()
        db.close()
