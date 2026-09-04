"""S6 验证：IP 地理位置（教材版本 / 地区 / 天气）

覆盖：
- ip_geolocation：BDC 响应解析（省份代码提取）、私有 IP 跳过、缓存命中、ipinfo 降级
- region 路由：resolve（返回结构）、auto-fill（自动写 city）、from-pref（读 city）、health
- textbook：resolve_textbook_id 按省份匹配（region 版本优先于全国通用版本）
- 迁移 061：region 列 + 索引（幂等）

铁律：外部 HTTP 全部 monkeypatch 打桩，绝不真实调 BigDataCloud/ipinfo/和风。
"""
import pytest

from app.database import SessionLocal
from app.models.textbook import TextbookVersion, UserTextbookPref
from app.domains.platform.services import ip_geolocation
from app.domains.content.routers.textbook import resolve_textbook_id


# ── mock BDC 响应（参照真实结构：湖北荆门）──

def _mock_bdc_hubei(ip: str = "13.212.225.30") -> dict:
    return {
        "ip": ip,
        "country": {"isoAlpha2": "CN", "isoAlpha3": "CHN",
                    "name": "中国", "isoName": "China"},
        "location": {
            "city": "荆门市", "localityName": "掇刀区",
            "latitude": 30.99, "longitude": 112.19,
            "timeZone": {"ianaTimeId": "Asia/Shanghai"},
        },
        "localityInfo": {
            "administrative": [
                {"name": "中国", "adminLevel": 2, "isoCode": "CN"},
                {"name": "湖北省", "adminLevel": 4, "chinaAdminCode": "42"},
                {"name": "荆门市", "adminLevel": 5, "chinaAdminCode": "42 08"},
                {"name": "掇刀区", "adminLevel": 6, "chinaAdminCode": "42 08 04"},
            ],
        },
        "network": {"organisation": "Amazon.com, Inc."},
    }


def _mock_bdc_shanghai(ip: str = "1.2.3.4") -> dict:
    return {
        "ip": ip,
        "country": {"isoAlpha2": "CN", "name": "中国", "isoName": "China"},
        "location": {"city": "上海市", "latitude": 31.23, "longitude": 121.47,
                     "timeZone": {"ianaTimeId": "Asia/Shanghai"}},
        "localityInfo": {"administrative": [
            {"name": "中国", "adminLevel": 2, "isoCode": "CN"},
            {"name": "上海市", "adminLevel": 4, "chinaAdminCode": "31"},
            {"name": "上海市", "adminLevel": 5, "chinaAdminCode": "31 01"},
        ]},
        "network": {"organisation": "China Telecom"},
    }


# ═══════════════ ip_geolocation 单元测试 ═══════════════

def test_ipgeo_parse_bdc_province():
    geo = ip_geolocation._parse_bdc_response("13.212.225.30", _mock_bdc_hubei())
    assert geo.country_code == "CN"
    assert geo.province_code == "42"
    assert geo.province_name == "湖北省"
    assert geo.city == "荆门市"
    assert geo.district == "掇刀区"
    assert geo.latitude == 30.99
    assert geo.timezone == "Asia/Shanghai"
    assert geo.source == "bigdatacloud"


def test_ipgeo_parse_bdc_shanghai():
    geo = ip_geolocation._parse_bdc_response("1.2.3.4", _mock_bdc_shanghai())
    assert geo.province_code == "31"
    assert geo.province_name == "上海市"
    assert geo.city == "上海市"


def test_ipgeo_private_ip_skips(monkeypatch):
    called = []
    monkeypatch.setattr(ip_geolocation, "_fetch_bdc",
                        lambda ip: called.append(ip) or None)
    ip_geolocation.cache_clear()
    assert ip_geolocation.get_geo_by_ip("192.168.1.1") is None
    assert ip_geolocation.get_geo_by_ip("10.0.0.1") is None
    assert ip_geolocation.get_geo_by_ip("127.0.0.1") is None
    assert called == []  # 私有 IP 不应触发外部调用


def test_ipgeo_cache_hit(monkeypatch):
    monkeypatch.setattr(ip_geolocation, "_fetch_bdc",
                        lambda ip: ip_geolocation._parse_bdc_response(
                            ip, _mock_bdc_hubei(ip)))
    monkeypatch.setattr(ip_geolocation, "_ipinfo_token", lambda: "")
    ip_geolocation.cache_clear()
    g1 = ip_geolocation.get_geo_by_ip("8.8.8.8")
    g2 = ip_geolocation.get_geo_by_ip("8.8.8.8")
    assert g1 is not None and g1.province_code == "42"
    assert g2 is not None
    assert ip_geolocation.cache_size() >= 1


def test_ipgeo_ipinfo_fallback(monkeypatch):
    # BDC 失败 → 降级 ipinfo（有 token 时）
    monkeypatch.setattr(ip_geolocation, "_fetch_bdc", lambda ip: None)
    monkeypatch.setattr(ip_geolocation, "_ipinfo_token", lambda: "tok")
    monkeypatch.setattr(ip_geolocation, "_fetch_ipinfo",
                        lambda ip: ip_geolocation._GeoInfo(
                            ip=ip, country_code="CN", city="北京", source="ipinfo"))
    ip_geolocation.cache_clear()
    geo = ip_geolocation.get_geo_by_ip("114.114.114.114")
    assert geo is not None
    assert geo.source == "ipinfo"
    assert geo.city == "北京"


def test_ipgeo_no_fallback_when_no_token(monkeypatch):
    monkeypatch.setattr(ip_geolocation, "_fetch_bdc", lambda ip: None)
    monkeypatch.setattr(ip_geolocation, "_ipinfo_token", lambda: "")
    ip_geolocation.cache_clear()
    assert ip_geolocation.get_geo_by_ip("203.0.113.7") is None


# ═══════════════ region 路由集成测试 ═══════════════

@pytest.fixture
def _mock_geo(monkeypatch):
    """打桩：让 region 路由的 IP 解析返回固定湖北 geo，不触网。"""
    def fake_get_geo(ip, use_cache=True):
        return ip_geolocation._parse_bdc_response(ip, _mock_bdc_hubei(ip))
    monkeypatch.setattr(ip_geolocation, "get_geo_by_ip", fake_get_geo)
    ip_geolocation.cache_clear()
    return fake_get_geo


def test_region_resolve(client, _mock_geo):
    r = client.get("/api/region/resolve?ip=13.212.225.30")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["country_code"] == "CN"
    assert body["province_code"] == "42"
    assert body["province_name"] == "湖北省"
    assert body["city"] == "荆门市"
    assert body["source"] == "bigdatacloud"


def test_region_resolve_unresolved(client, monkeypatch):
    monkeypatch.setattr(ip_geolocation, "get_geo_by_ip", lambda ip, use_cache=True: None)
    ip_geolocation.cache_clear()
    r = client.get("/api/region/resolve?ip=192.168.1.1")
    assert r.status_code == 200
    assert r.json()["source"] == "unresolved"
    assert r.json()["province_code"] == ""


def test_region_auto_fill_writes_city(client, _mock_geo):
    # AuthClient 会在请求时自动为该 user_id mint token 并创建用户（city 为空）
    r = client.post("/api/region/auto-fill", json={"user_id": "s6_geo_user"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["city"] == "荆门市"
    assert body["province_code"] == "42"

    # 二次调用：city 已存在 → 跳过不覆盖
    r2 = client.post("/api/region/auto-fill", json={"user_id": "s6_geo_user"})
    assert r2.json()["skipped"] is True


def test_region_auto_fill_force(client, _mock_geo):
    # 先写一次（city=荆门市），再 force=True 覆盖（mock 仍返回荆门市，验证走 force 分支）
    client.post("/api/region/auto-fill", json={"user_id": "s6_geo_user2"})
    r = client.post("/api/region/auto-fill",
                    json={"user_id": "s6_geo_user2", "force": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["city"] == "荆门市"


def test_region_from_pref(client, _mock_geo):
    # 先 auto-fill 写入 city，再 from-pref 读
    client.post("/api/region/auto-fill", json={"user_id": "s6_geo_user3"})
    r = client.get("/api/region/from-pref?user_id=s6_geo_user3")
    assert r.status_code == 200
    assert r.json()["city"] == "荆门市"


def test_region_auto_fill_ip_resolve_fail(client, monkeypatch):
    # IP 解析失败 → 返回 ok=False（降级，不写 city，也不报错）
    monkeypatch.setattr(ip_geolocation, "get_geo_by_ip", lambda ip, use_cache=True: None)
    r = client.post("/api/region/auto-fill", json={"user_id": "s6_geo_user4"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["reason"] == "IP 解析失败"


def test_region_health(client):
    r = client.get("/api/region/health")
    assert r.status_code == 200
    assert "cache_size" in r.json()


# ═══════════════ textbook 省份匹配 ═══════════════

@pytest.fixture
def _textbook_seed():
    """建：英语 6 年级 通用版(人教版 region='') + 上海版(沪教版 region='31')"""
    db = SessionLocal()
    # 清理旧
    for old in db.query(TextbookVersion).filter(
            TextbookVersion.name.in_(["S6通用版", "S6上海版"])).all():
        db.delete(old)
    db.commit()
    common = TextbookVersion(subject="英语", grade=6, name="S6通用版",
                             sort_order=1, enabled=True, region="")
    sh = TextbookVersion(subject="英语", grade=6, name="S6上海版",
                         sort_order=0, enabled=True, region="31")
    db.add_all([common, sh]); db.commit()
    db.refresh(common); db.refresh(sh)
    # 清理用户 pref
    db.query(UserTextbookPref).filter(
        UserTextbookPref.user_id == "s6_tb_user").delete()
    db.commit()
    yield {"common": common, "sh": sh}
    # 清理
    db.query(UserTextbookPref).filter(
        UserTextbookPref.user_id == "s6_tb_user").delete()
    for t in (common, sh):
        db.delete(t)
    db.commit(); db.close()


def test_textbook_province_match_shanghai(_textbook_seed):
    db = SessionLocal()
    tid = resolve_textbook_id(db, "s6_tb_user", "英语", 6, province_code="31")
    db.close()
    assert tid == _textbook_seed["sh"].id  # 上海用户 → 沪教版


def test_textbook_province_match_default(_textbook_seed):
    db = SessionLocal()
    tid = resolve_textbook_id(db, "s6_tb_user", "英语", 6, province_code="11")
    db.close()
    assert tid == _textbook_seed["common"].id  # 北京无专用版 → 全国通用版


def test_textbook_no_province_falls_back_default(_textbook_seed):
    db = SessionLocal()
    tid = resolve_textbook_id(db, "s6_tb_user", "英语", 6, province_code="")
    db.close()
    assert tid == _textbook_seed["common"].id  # 无省份 → 通用版


def test_textbook_user_pref_overrides_province(_textbook_seed):
    db = SessionLocal()
    pref = UserTextbookPref(user_id="s6_tb_user", subject="英语",
                            textbook_id=_textbook_seed["common"].id)
    db.add(pref); db.commit()
    # 上海用户但手动选了通用版 → 尊重用户选择
    tid = resolve_textbook_id(db, "s6_tb_user", "英语", 6, province_code="31")
    db.close()
    assert tid == _textbook_seed["common"].id
