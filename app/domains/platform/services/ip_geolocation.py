"""IP 地理位置解析服务（BigDataCloud + ipinfo.io 兼容）

- 主服务：BigDataCloud IP Geolocation API（https://api-bdc.net/data/ip-geolocation）
  返回 country/region/city/经纬度/时区/中国行政编码（chinaAdminCode 前 2 位 = 省份代码）。
- 备用：ipinfo.io（ipinfo.io/{ip}/json），仅返回 city（无省份/经纬度）；
  仅当 BDC API 不可用时使用，且仅作为天气兜底。
- 缓存：进程内 LRU 4 小时（key=IP，TTL=4*3600s）。
- 配置：从 .env / system_config 读 BDC_API_KEY / IPINFO_API_TOKEN。

铁律：绝不在持 DB 连接时调外部 API；调用方需自行安排 DB 段（with SessionLocal()）。
"""
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from fastapi import Request

from . import sysconfig

logger = logging.getLogger(__name__)

# ═══════════════ 缓存 ═══════════════

_CACHE_TTL = 4 * 3600  # 4 小时
_CACHE_MAX = 4096      # 最多缓存 4096 个 IP（LRU 截断）
_ip_cache: "dict[str, tuple[float, Optional['_GeoInfo']]]" = {}


def _cache_get(ip: str) -> Optional["_GeoInfo"]:
    hit = _ip_cache.get(ip)
    if not hit:
        return None
    ts, geo = hit
    if time.time() - ts > _CACHE_TTL:
        _ip_cache.pop(ip, None)
        return None
    return geo


def _cache_put(ip: str, geo: Optional["_GeoInfo"]) -> None:
    if len(_ip_cache) >= _CACHE_MAX:
        # 简单 FIFO 截断（删最旧 10%）
        old_keys = sorted(_ip_cache, key=lambda k: _ip_cache[k][0])[: _CACHE_MAX // 10]
        for k in old_keys:
            _ip_cache.pop(k, None)
    _ip_cache[ip] = (time.time(), geo)


def cache_clear() -> None:
    """测试用：清空 IP 缓存"""
    _ip_cache.clear()


def cache_size() -> int:
    return len(_ip_cache)


# ═══════════════ 数据类 ═══════════════

@dataclass
class _GeoInfo:
    """IP 地理位置解析结果"""
    ip: str
    country_code: str = ""       # ISO 3166-1 Alpha-2，如 CN
    country_name: str = ""       # China
    province_code: str = ""      # 中国省份代码（chinaAdminCode 前 2 位），如 31=上海；海外空
    province_name: str = ""      # 上海市
    city: str = ""               # 上海市 / Jingmen Shi
    district: str = ""           # 区/县（localityName）
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = ""           # Asia/Shanghai
    isp: str = ""                # 运营商/组织（可选）
    source: str = ""             # bigdatacloud / ipinfo / cache

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════ IP 提取 ═══════════════

def get_client_ip(request: Request) -> str:
    """从 FastAPI Request 提取真实客户端 IP（按 X-Forwarded-For > X-Real-IP > client.host 顺序）"""
    if not request:
        return ""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host or ""
    return ""


# ═══════════════ BigDataCloud API 封装 ═══════════════

BDC_ENDPOINT = "https://api-bdc.net/data/ip-geolocation"
IPINFO_ENDPOINT = "https://ipinfo.io/{ip}/json"


def _bdc_api_key() -> str:
    """BDC API key（注册免费版可获 basic fields；无 key 也可调，但有配额/限流）"""
    return sysconfig.get("BDC_API_KEY") or os.environ.get("BDC_API_KEY", "")


def _ipinfo_token() -> str:
    """ipinfo.io token（备用）"""
    return sysconfig.get("IPINFO_API_TOKEN") or os.environ.get("IPINFO_API_TOKEN", "")


def _is_private_ip(ip: str) -> bool:
    """判断是否内网/保留 IP（无需调外部 API）"""
    if not ip:
        return True
    parts = ip.split(".")
    if len(parts) != 4:
        # IPv6 或异常格式：粗略放过，由 BDC 自行处理
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return True
    if a == 10:
        return True
    if a == 127:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 0:
        return True
    return False


def _parse_bdc_response(ip: str, data: dict) -> _GeoInfo:
    """解析 BigDataCloud 响应为 _GeoInfo"""
    country = data.get("country") or {}
    location = data.get("location") or {}
    network = data.get("network") or {}
    locality_info = data.get("localityInfo") or {}
    administrative = locality_info.get("administrative") or []

    # 中国省份：administrative[1] 必有 chinaAdminCode（"31"=上海）
    # 中国省级 adminLevel=4（province）；市级 adminLevel=5（city/prefecture）
    province_code = ""
    province_name = ""
    city = ""
    district = ""
    for adm in administrative:
        china_code = adm.get("chinaAdminCode") or ""
        level = adm.get("adminLevel")
        # localityLanguage=zh 时 name 为中文，isoName 为英文；优先中文
        name = adm.get("name") or adm.get("isoName") or ""
        if not china_code:
            continue
        if level == 4 and not province_code:
            # 省/直辖市/自治区（chinaAdminCode 前 2 位）
            province_code = china_code[:2]
            province_name = name
        elif level == 5 and not city:
            city = name
        elif level == 6 and not district:
            district = name

    return _GeoInfo(
        ip=ip,
        country_code=country.get("isoAlpha2") or "",
        country_name=country.get("name") or country.get("isoName") or "",
        province_code=province_code,
        province_name=province_name,
        city=city or location.get("city") or location.get("localityName") or "",
        district=district,
        latitude=float(location.get("latitude") or 0.0),
        longitude=float(location.get("longitude") or 0.0),
        timezone=(location.get("timeZone") or {}).get("ianaTimeId") or "",
        isp=network.get("organisation") or "",
        source="bigdatacloud",
    )


def _fetch_bdc(ip: str) -> Optional[_GeoInfo]:
    """调用 BigDataCloud IP Geolocation API；返回 None 表示失败/跳过"""
    if _is_private_ip(ip):
        return None
    params = {"ip": ip, "localityLanguage": "zh"}
    key = _bdc_api_key()
    if key:
        params["key"] = key
    try:
        r = requests.get(BDC_ENDPOINT, params=params, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return _parse_bdc_response(ip, data)
        logger.warning("BDC API 返回 %s（ip=%s）: %s", r.status_code, ip, r.text[:200])
        return None
    except requests.RequestException as e:
        logger.warning("BDC API 调用失败（ip=%s）: %s", ip, e)
        return None
    except Exception as e:
        logger.warning("BDC API 解析失败（ip=%s）: %s", ip, e)
        return None


def _fetch_ipinfo(ip: str) -> Optional[_GeoInfo]:
    """ipinfo.io 备用：仅返回 city（无 province/经纬度）"""
    if _is_private_ip(ip):
        return None
    try:
        url = IPINFO_ENDPOINT.format(ip=ip)
        token = _ipinfo_token()
        if token:
            url += f"?token={token}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return _GeoInfo(
                ip=ip,
                country_code=data.get("country") or "",
                country_name="",
                city=data.get("city") or "",
                province_name=data.get("region") or "",
                latitude=0.0,
                longitude=0.0,
                timezone=data.get("timezone") or "",
                isp=data.get("org") or "",
                source="ipinfo",
            )
        return None
    except Exception as e:
        logger.warning("ipinfo API 调用失败（ip=%s）: %s", ip, e)
        return None


# ═══════════════ 公共 API ═══════════════

def get_geo_by_ip(ip: str, *, use_cache: bool = True) -> Optional[_GeoInfo]:
    """根据 IP 获取地理位置；缓存优先，失败返回 None。

    私有/保留 IP（10.x、172.16-31.x、192.168.x、127.x、0.x）直接返回 None，
    不打缓存也不调外部 API（这类 IP 无法地理定位，且避免无谓请求）。
    """
    ip = (ip or "").strip()
    if not ip or _is_private_ip(ip):
        return None
    if use_cache:
        hit = _cache_get(ip)
        if hit is not None:
            hit.source = hit.source or "cache"
            return hit

    geo = _fetch_bdc(ip)
    if geo is None and _ipinfo_token():
        geo = _fetch_ipinfo(ip)
    if geo is None:
        # 缓存 None 也缓存（避免同一 IP 反复打外部），但 TTL 缩短为 1 分钟
        _ip_cache[ip] = (time.time() - _CACHE_TTL + 60, None)
        return None
    _cache_put(ip, geo)
    return geo


def get_geo_by_request(request: Request, *, use_cache: bool = True) -> Optional[_GeoInfo]:
    """从 FastAPI Request 提 IP 并解析（最常用入口）"""
    ip = get_client_ip(request)
    return get_geo_by_ip(ip, use_cache=use_cache) if ip else None


def get_province_code_by_ip(ip: str) -> str:
    """便捷方法：仅返回省份代码（chinaAdminCode 前 2 位）；海外/失败返回空"""
    geo = get_geo_by_ip(ip)
    return geo.province_code if geo else ""


def get_city_by_ip(ip: str, default: str = "") -> str:
    """便捷方法：仅返回 city；供 weather.py 兜底"""
    geo = get_geo_by_ip(ip)
    return geo.city if (geo and geo.city) else default


__all__ = [
    "get_geo_by_ip", "get_geo_by_request", "get_client_ip",
    "get_province_code_by_ip", "get_city_by_ip",
    "cache_clear", "cache_size",
]
