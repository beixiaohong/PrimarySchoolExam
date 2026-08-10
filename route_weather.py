import json
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from backend.base_config import localconfig
from backend.public import jwt
from backend.public.redis_client import get_redis_safe
from sqlalchemy.orm import Session
from backend.model import database, model_user
from backend.users import user_auth

# 创建一个 APIRouter 实例，用于处理天气相关的 API 请求
Weather = APIRouter()



# 验证用户登录状态和积分的依赖项
def verify_user_points(min_points: int = 4):
    def _verify_user_points(
        db: Session = Depends(user_auth.get_db),
        user: model_user.ModUser = Depends(user_auth.get_current_user_or_401)
    ):
        # 检查积分是否足够
        if user.points < min_points:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"积分不足，需要{min_points}积分，当前积分: {user.points}",
            )
        return user
    return _verify_user_points

# ============================================================
# 首页天气（无需登录，不扣积分，Redis 4h 缓存）
# ============================================================

# IP 地理信息缓存（避免对同一 IP 重复请求 ipinfo.io）
_ip_cache = {}
_IP_CACHE_TTL = 14400  # 4小时


def _get_client_ip(request: Request) -> str:
    """从请求中获取客户端真实 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


def _get_location_by_ip(ip: str) -> dict:
    """通过 ipinfo.io 获取 IP 的地理信息"""
    now = datetime.now().timestamp()
    if ip in _ip_cache:
        cached, ts = _ip_cache[ip]
        if now - ts < _IP_CACHE_TTL:
            return cached
    
    try:
        token = localconfig.geoipconfig.IPINFO_API_TOKEN
        url = f"https://ipinfo.io/{ip}/json"
        if token:
            url += f"?token={token}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        loc = data.get("loc", "39.9,116.4").split(",")
        result = {
            "lat": loc[0] if len(loc) > 0 else "39.9",
            "lon": loc[1] if len(loc) > 1 else "116.4",
            "city": data.get("city", "北京"),
            "region": data.get("region", ""),
        }
        _ip_cache[ip] = (result, now)
        return result
    except Exception:
        return {"lat": "39.9", "lon": "116.4", "city": "北京", "region": ""}


@Weather.get("/current", summary="首页天气（IP定位 + Redis缓存）")
def get_current_weather(request: Request):
    """
    根据客户端 IP 自动获取当地天气
    
    - 无需登录，不扣积分
    - 相同地区 4 小时内不重复请求外部 API（Redis 缓存）
    - Redis 不可用时降级为直接调用 API
    """
    # 1. 获取 IP 和地理位置
    client_ip = _get_client_ip(request)
    location = _get_location_by_ip(client_ip)
    lon, lat = location["lon"], location["lat"]
    
    # 2. 检查 Redis 缓存
    r = get_redis_safe()
    cache_key = f"weather:current:{lon},{lat}"
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                result = json.loads(cached)
                result["cached"] = True
                return result
        except Exception:
            pass
    
    # 3. 调用和风 GeoAPI 获取 location_id
    api_host = localconfig.qweather.weather_api_host
    api_key = localconfig.qweather.weather_api_key
    auth_token = jwt.qjwt.encoded_jwt
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    try:
        geo_url = f"https://geoapi.qweather.com/v2/city/lookup?location={lon},{lat}&key={api_key}"
        geo_resp = requests.get(geo_url, timeout=10)
        geo_data = geo_resp.json()
        if geo_data.get("code") != "200" or not geo_data.get("location"):
            return {"city": location["city"], "now": None, "forecast": [], "error": "城市查找失败"}
        
        loc_info = geo_data["location"][0]
        location_id = loc_info["id"]
        city_name = loc_info.get("name", location["city"])
        
        # 4. 获取实时天气
        now_url = f"https://{api_host}/v7/weather/now?location={location_id}"
        now_resp = requests.get(now_url, headers=headers, timeout=10)
        now_data = now_resp.json()
        
        # 5. 获取 3 天预报
        forecast_url = f"https://{api_host}/v7/weather/3d?location={location_id}"
        forecast_resp = requests.get(forecast_url, headers=headers, timeout=10)
        forecast_data = forecast_resp.json()
        
        result = {
            "city": city_name,
            "now": now_data.get("now") if now_data.get("code") == "200" else None,
            "forecast": forecast_data.get("daily", []) if forecast_data.get("code") == "200" else [],
            "update_time": datetime.now().isoformat(),
            "cached": False,
        }
        
        # 6. 写入 Redis 缓存（4小时）
        if r:
            try:
                r.setex(cache_key, 14400, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        
        return result
        
    except Exception as e:
        return {"city": location["city"], "now": None, "forecast": [], "error": str(e)}


# ============================================================
# 需要登录的天气接口（注意：/{city} 必须在 /current 之后定义，避免路由冲突）
# ============================================================

# 定义一个获取天气信息的路由，需要登录和至少1积分
@Weather.get("/{city}")
def get_weather(
    city: str,
    db: Session = Depends(user_auth.get_db),
    user: model_user.ModUser = Depends(verify_user_points(1))
):
    """
    根据城市名称获取天气信息
    
    参数:
    city (str): 城市名称
    
    返回:
    weather_data (dict): 天气信息的字典
    """
    # 扣除积分
    if not user_auth.deduct_user_points(db, user, 1):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"积分扣除失败，当前积分: {user.points}"
        )
        
    # OpenWeatherMap API 的 URL
    url = f"https://geoapi.qweather.com/v2/city/lookup?location={city}&key={localconfig.qweather.weather_api_key}"
    # 发送 GET 请求
    response = requests.get(url)
    # 检查响应状态码
    response.raise_for_status()
    # 将响应的 JSON 数据解析为字典
    weather_data = response.json()
    # 返回天气信息
    return {
        "weather_data": weather_data,
        "remaining_points": user.points
    }

# 定义另一个获取天气信息的路由，需要登录和至少1积分
@Weather.get("2/{location}")
def get_weather2(
    location: str,
    db: Session = Depends(user_auth.get_db),
    user: model_user.ModUser = Depends(verify_user_points(1))
):
    """
    根据经纬度获取天气信息
    
    参数:
    location (str): 经纬度字符串
    
    返回:
    weather_data (dict): 天气信息的字典
    """
    # 扣除积分
    if not user_auth.deduct_user_points(db, user, 1):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"积分扣除失败，当前积分: {user.points}"
        )
        
    # OpenWeatherMap API 的 URL
    url = f"https://{localconfig.qweather.weather_api_host}/v7/weather/now?location={location}"
    # 设置请求头，包含授权信息
    headers = {
        "Authorization": f"Bearer {jwt.qjwt.encoded_jwt}"
    }
    # 发送 GET 请求
    response = requests.get(url, headers=headers)
    # 检查响应状态码
    response.raise_for_status()
    # 将响应的 JSON 数据解析为字典
    weather_data = response.json()
    # 返回天气信息
    return {
        "weather_data": weather_data,
        "remaining_points": user.points
    }