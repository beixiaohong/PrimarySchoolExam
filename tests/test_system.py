"""系统级冒烟：健康检查 + 前端首页"""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    # OBS-03 增强后健康检查包含 status + checks（DB/迁移/uptime）
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data
    assert "db" in data["checks"]
    assert "uptime_sec" in data["checks"]


def test_index_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "html" in r.headers.get("content-type", "").lower()
