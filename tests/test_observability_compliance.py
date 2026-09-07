"""可观测性 + 合规底座测试

覆盖：
- OBS-03: /health 端点增强（DB 连接 / 迁移版本 / uptime）
- OBS-04: /api/metrics 运营指标端点
- OBS-05: 慢查询日志安装
- CMP-02: 监护人同意记录 / 查询 / 撤回
- CMP-06: 数据导出申请 / 数据删除申请
"""
import pytest
from datetime import datetime


# ── OBS-03: /health 增强 ──

class TestHealthEndpoint:
    """健康检查端点增强测试"""

    def test_health_returns_ok(self, client):
        """健康检查返回 status=ok + checks 字典"""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "checks" in data

    def test_health_has_db_check(self, client):
        """健康检查包含 DB 连接状态"""
        resp = client.get("/health")
        data = resp.json()
        assert "db" in data["checks"]
        assert data["checks"]["db"] == "ok"

    def test_health_has_migrations(self, client):
        """健康检查包含迁移版本"""
        resp = client.get("/health")
        data = resp.json()
        assert "migrations" in data["checks"]
        # 迁移版本应该是字符串（最新的迁移名）
        assert isinstance(data["checks"]["migrations"], str)

    def test_health_has_uptime(self, client):
        """健康检查包含 uptime（秒）"""
        resp = client.get("/health")
        data = resp.json()
        assert "uptime_sec" in data["checks"]
        assert isinstance(data["checks"]["uptime_sec"], (int, float))
        assert data["checks"]["uptime_sec"] >= 0


# ── OBS-04: /api/metrics 运营指标 ──

class TestMetricsEndpoint:
    """运营指标端点测试"""

    def test_metrics_returns_200(self, client):
        """指标端点返回 200"""
        resp = client.get("/api/metrics")
        assert resp.status_code == 200

    def test_metrics_has_generated_at(self, client):
        """指标包含生成时间"""
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "generated_at" in data

    def test_metrics_has_dau(self, client):
        """指标包含 DAU"""
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "dau" in data
        # DAU 应该是整数或 None
        assert data["dau"] is None or isinstance(data["dau"], int)

    def test_metrics_has_answers(self, client):
        """指标包含答题量"""
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "answers" in data

    def test_metrics_has_ai_calls(self, client):
        """指标包含 AI 调用量"""
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "ai_calls" in data

    def test_metrics_has_total_users(self, client):
        """指标包含总用户数"""
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "total_users" in data
        # 总用户数应该是整数或 None（查询失败时）
        assert data["total_users"] is None or isinstance(data["total_users"], int)

    def test_metrics_has_migration_version(self, client):
        """指标包含迁移版本"""
        resp = client.get("/api/metrics")
        data = resp.json()
        assert "migration_version" in data


# ── OBS-05: 慢查询日志 ──

class TestSlowQueryListener:
    """慢查询日志安装测试"""

    def test_listener_installed(self):
        """慢查询监听器已安装"""
        from app.core.slow_query import _installed
        # 应用导入时会安装监听器
        assert _installed is True

    def test_listener_idempotent(self):
        """慢查询监听器幂等（多次调用只装一次）"""
        from app.core.slow_query import install_slow_query_listener
        from app.database import engine
        # 再次调用应该返回 True 且不重复安装
        result = install_slow_query_listener(engine)
        assert result is True


# ── CMP-02: 监护人同意 ──

class TestGuardianConsent:
    """监护人同意接口测试"""

    def test_record_consent(self, client):
        """记录监护人同意"""
        resp = client.post("/api/compliance/consent", json={
            "guardian_name": "张三",
            "rule_version": "v1.0",
        }, params={"user_id": "test_consent_user"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("consented", "already_consent")
        assert data["rule_version"] == "v1.0"

    def test_get_consent_status(self, client):
        """查询同意状态"""
        # 先记录同意
        client.post("/api/compliance/consent", json={
            "rule_version": "v1.0",
        }, params={"user_id": "test_consent_query"})
        # 查询
        resp = client.get("/api/compliance/consent", params={"user_id": "test_consent_query"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_rule_version"] == "v1.0"
        assert data["has_current_consent"] is True

    def test_consent_idempotent(self, client):
        """重复同意幂等返回"""
        # 第一次
        resp1 = client.post("/api/compliance/consent", json={
            "rule_version": "v1.0",
        }, params={"user_id": "test_consent_idem"})
        assert resp1.json()["status"] == "consented"
        # 第二次（幂等）
        resp2 = client.post("/api/compliance/consent", json={
            "rule_version": "v1.0",
        }, params={"user_id": "test_consent_idem"})
        assert resp2.json()["status"] == "already_consent"

    def test_revoke_consent(self, client):
        """撤回同意"""
        # 先同意
        client.post("/api/compliance/consent", json={
            "rule_version": "v1.0",
        }, params={"user_id": "test_consent_revoke"})
        # 撤回
        resp = client.post("/api/compliance/consent/revoke",
                          params={"user_id": "test_consent_revoke"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"

    def test_revoke_without_consent_404(self, client):
        """无同意记录时撤回返回 404"""
        resp = client.post("/api/compliance/consent/revoke",
                          params={"user_id": "test_no_consent_user"})
        assert resp.status_code == 404


# ── CMP-06: 数据导出 ──

class TestDataExport:
    """数据导出接口测试"""

    def test_request_export(self, client):
        """申请数据导出"""
        resp = client.post("/api/compliance/export",
                          params={"user_id": "test_export_user"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("created", "already_pending")
        assert "request_id" in data

    def test_get_export_status(self, client):
        """查询导出状态"""
        # 先申请
        client.post("/api/compliance/export",
                   params={"user_id": "test_export_query"})
        # 查询
        resp = client.get("/api/compliance/export",
                         params={"user_id": "test_export_query"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_request"] is True
        assert data["status"] == "pending"

    def test_no_export_request(self, client):
        """无导出申请时返回 has_request=False"""
        resp = client.get("/api/compliance/export",
                         params={"user_id": "test_no_export_user"})
        assert resp.status_code == 200
        assert resp.json()["has_request"] is False


# ── CMP-06: 数据删除 ──

class TestDataDeletion:
    """数据删除接口测试"""

    def test_request_delete(self, client):
        """申请数据删除"""
        resp = client.post("/api/compliance/delete", json={
            "reason": "不再使用",
        }, params={"user_id": "test_delete_user"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["state"] == "pending"

    def test_duplicate_delete_rejected(self, client):
        """重复删除申请被拒绝"""
        # 第一次
        client.post("/api/compliance/delete", json={
            "reason": "不再使用",
        }, params={"user_id": "test_delete_dup"})
        # 第二次（冲突）
        resp = client.post("/api/compliance/delete", json={
            "reason": "再次申请",
        }, params={"user_id": "test_delete_dup"})
        assert resp.status_code == 409

    def test_get_delete_status(self, client):
        """查询删除状态"""
        # 先申请
        client.post("/api/compliance/delete", json={
            "reason": "测试",
        }, params={"user_id": "test_delete_query"})
        # 查询
        resp = client.get("/api/compliance/delete",
                         params={"user_id": "test_delete_query"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_request"] is True
        assert data["status"] == "pending"


# ── CMP: 规则查询 ──

class TestComplianceRules:
    """规则查询接口测试"""

    def test_get_rules(self, client):
        """获取隐私规则（无需登录）"""
        resp = client.get("/api/compliance/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_version" in data
        assert "summary" in data
        assert data["current_version"] == "v1.0"
