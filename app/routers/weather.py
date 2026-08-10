"""天气系统（移植自 route_weather.py，剥离 jwt/redis/积分体系）

- 和风天气 GeoAPI 查城市 → /v7/weather/now 实时 + /v7/weather/3d 三日预报
- 无 Redis：进程内 dict 缓存（key=城市，TTL 4 小时）
- 城市解析顺序：query city → users.city（传 user_id 时）→ IP 定位（ipinfo.io）→ 默认城市
- 配置从 .env 读：QWEATHER_API_KEY、QWEATHER_API_HOST、IPINFO_API_TOKEN
"""
import logging
import os
import time
from datetime import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

QWEATHER_API_KEY = os.environ.get("QWEATHER_API_KEY", "").strip()
QWEATHER_API_HOST = (os.environ.get("QWEATHER_API_HOST", "").strip() or "api.qweather.com")
IPINFO_API_TOKEN = os.environ.get("IPINFO_API_TOKEN", "").strip()
DEFAULT_CITY = os.environ.get("WEATHER_DEFAULT_CITY", "").strip() or "北京"

_CACHE_TTL = 4 * 3600      # 天气缓存 4 小时
_IP_CACHE_TTL = 4 * 3600   # IP 定位缓存 4 小时
_weather_cache: dict = {}
_ip_cache: dict = {}


def weather_configured() -> bool:
    return bool(QWEATHER_API_KEY)


class CitySaveReq(BaseModel):
    user_id: str
    city: str


# ═══════════════ 城市解析 ═══════════════

def _get_client_ip(request: Request) -> str:
    """从请求中获取客户端真实 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


def _get_city_by_ip(ip: str) -> str:
    """通过 ipinfo.io 解析 IP 所在城市，失败回退默认城市"""
    now = time.time()
    if ip in _ip_cache:
        city, ts = _ip_cache[ip]
        if now - ts < _IP_CACHE_TTL:
            return city
    try:
        url = f"https://ipinfo.io/{ip}/json"
        if IPINFO_API_TOKEN:
            url += f"?token={IPINFO_API_TOKEN}"
        data = requests.get(url, timeout=5).json()
        city = data.get("city") or DEFAULT_CITY
        _ip_cache[ip] = (city, now)
        return city
    except Exception:
        logger.warning("IP 定位失败（ip=%s），回退默认城市", ip)
        return DEFAULT_CITY


# ═══════════════ 和风天气调用 ═══════════════

def _fetch_weather(city_query: str) -> dict:
    """GeoAPI 查城市 → 实时天气 + 3 日预报"""
    params_key = {"key": QWEATHER_API_KEY}
    try:
        geo = requests.get(
            "https://geoapi.qweather.com/v2/city/lookup",
            params={**params_key, "location": city_query}, timeout=10).json()
        if geo.get("code") != "200" or not geo.get("location"):
            return {"city": city_query, "now": None, "forecast": [], "error": "未找到该城市"}
        loc = geo["location"][0]
        location_id, city_name = loc["id"], loc.get("name", city_query)

        now_data = requests.get(
            f"https://{QWEATHER_API_HOST}/v7/weather/now",
            params={**params_key, "location": location_id}, timeout=10).json()
        forecast_data = requests.get(
            f"https://{QWEATHER_API_HOST}/v7/weather/3d",
            params={**params_key, "location": location_id}, timeout=10).json()

        return {
            "city": city_name,
            "now": now_data.get("now") if now_data.get("code") == "200" else None,
            "forecast": forecast_data.get("daily", []) if forecast_data.get("code") == "200" else [],
            "update_time": datetime.now().isoformat(timespec="seconds"),
        }
    except requests.RequestException as e:
        logger.warning("天气接口调用失败（city=%s）: %s", city_query, e)
        return {"city": city_query, "now": None, "forecast": [], "error": "天气服务暂不可用"}


# ═══════════════ 接口 ═══════════════

@router.get("/current", summary="当前天气（城市参数 > 用户配置城市 > IP 定位 > 默认城市）")
def get_current_weather(request: Request, city: str = None, user_id: str = None,
                        db: Session = Depends(get_db)):
    if not weather_configured():
        raise HTTPException(503, "天气服务未配置（QWEATHER_API_KEY）")

    target = (city or "").strip()
    if not target and user_id:
        user = db.query(User).filter(User.user_id == user_id.strip()).first()
        target = (user.city or "").strip() if user else ""
    if not target:
        target = _get_city_by_ip(_get_client_ip(request))

    cached = _weather_cache.get(target)
    if cached:
        result, ts = cached
        if time.time() - ts < _CACHE_TTL:
            return {**result, "cached": True}

    result = _fetch_weather(target)
    _weather_cache[target] = (result, time.time())
    return {**result, "cached": False}


@router.post("/city", summary="保存用户常用城市")
def save_city(req: CitySaveReq, db: Session = Depends(get_db)):
    city = (req.city or "").strip()
    if not city:
        raise HTTPException(400, "城市不能为空")
    if len(city) > 50:
        raise HTTPException(400, "城市名称过长")
    user = db.query(User).filter(User.user_id == req.user_id.strip()).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    user.city = city
    db.commit()
    return {"ok": True, "city": city}
