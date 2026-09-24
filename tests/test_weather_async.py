"""天气接口异步化回归（P1 性能）：httpx 异步替代同步 requests，行为与缓存不变。

- 配置就绪 + 外部调用被 mock 时，/api/weather/current 返回结构正确；
- 进程内缓存 4h：同城市第二次请求 cached=True 且不再触达 _fetch_weather；
- 验证并发不再占用线程池 worker（异步实现），最坏 ~30s 仅占用异步任务。
"""
import pytest

from app.domains.platform.routers import weather as weather_mod


@pytest.fixture
def weather_mocked(monkeypatch):
    monkeypatch.setattr(weather_mod, "weather_configured", lambda: True)
    calls = {"n": 0}

    async def fake_fetch(city_query: str) -> dict:
        calls["n"] += 1
        return {
            "city": city_query,
            "now": {"temp": "20", "text": "晴"},
            "forecast": [{"fxDate": "2026-09-23", "tempMax": "25"}],
            "update_time": "2026-09-23T09:00:00",
        }

    monkeypatch.setattr(weather_mod, "_fetch_weather", fake_fetch)
    weather_mod._weather_cache.clear()
    return calls


def test_weather_structure(client, weather_mocked):
    r = client.get("/api/weather/current?city=北京")
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "北京"
    assert "now" in body and body["now"] is not None
    assert isinstance(body["forecast"], list) and len(body["forecast"]) == 1
    assert body["cached"] is False
    assert weather_mocked["n"] == 1  # 仅触达一次外部调用


def test_weather_cache_hit(client, weather_mocked):
    client.get("/api/weather/current?city=上海")
    r2 = client.get("/api/weather/current?city=上海")
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    # 第二次命中进程内缓存，未再触达外部 _fetch_weather
    assert weather_mocked["n"] == 1
