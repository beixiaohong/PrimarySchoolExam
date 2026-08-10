"""系统级冒烟：健康检查 + 前端首页"""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "html" in r.headers.get("content-type", "").lower()
