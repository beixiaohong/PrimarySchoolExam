"""地区解析接口（基于 IP 地理位置服务）

- GET  /api/region/resolve          根据请求 IP 解析地理位置（不写库；轻量）
- POST /api/region/auto-fill        根据 IP 解析并自动写 users.city（仅 city 为空时）
- GET  /api/region/from-pref?user_id=  读取用户当前已配置的 city / region 偏好
- GET  /api/region/health           健康检查（缓存大小/可用性）

铁律：auto-fill 用短会话（with SessionLocal()），绝不持 DB 连接调外部 API。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.user import User

from ..services import ip_geolocation

logger = logging.getLogger(__name__)

router = APIRouter()


class AutoFillReq(BaseModel):
    user_id: str
    force: bool = False  # True 时强制覆盖（默认仅 city 为空才写）


@router.get("/resolve", summary="根据请求 IP 解析地理位置")
def resolve_region(request: Request, ip: str = ""):
    """根据请求 IP（或 query 传 ip）解析地理位置。

    返回：{ip, country_code, country_name, province_code, province_name, city, district, latitude, longitude, timezone, isp, source}
    - 缓存命中直接返回（4h TTL）；
    - 内部 IP / API 失败返回 200 但所有字段为空（前端可降级到手动选择）。

    副作用：无。无需家长密码。
    """
    target_ip = (ip or "").strip() or ip_geolocation.get_client_ip(request)
    geo = ip_geolocation.get_geo_by_ip(target_ip)
    if not geo:
        return {
            "ip": target_ip, "country_code": "", "country_name": "",
            "province_code": "", "province_name": "", "city": "", "district": "",
            "latitude": 0.0, "longitude": 0.0, "timezone": "", "isp": "",
            "source": "unresolved",
        }
    return geo.to_dict()


@router.post("/auto-fill", summary="根据 IP 解析自动写 users.city（仅 city 为空时）")
def auto_fill_region(req: AutoFillReq, request: Request):
    """根据请求 IP 解析地理位置，并自动写入 users.city。

    规则：
    - 默认仅当 users.city 为空时才写（force=False）；
    - force=True 时强制覆盖（用于用户主动「重新定位」操作）；
    - 用户不存在返回 404；
    - IP 解析失败返回 200 但 ok=False（前端可降级到手动选择）。

    持连铁律：先短会话查/写 user.city，立即关连接，再调外部 IP 服务。
    """
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise HTTPException(400, "user_id 不能为空")

    # ── 阶段 1：短会话读/写 city ──
    with SessionLocal() as db:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")
        if user.city and not req.force:
            return {
                "ok": False, "skipped": True, "reason": "city 已存在，未覆盖",
                "city": user.city,
            }

    # ── 阶段 2：调外部 IP 解析（DB 连接已释放）──
    target_ip = ip_geolocation.get_client_ip(request)
    geo = ip_geolocation.get_geo_by_ip(target_ip)
    if not geo or not geo.city:
        return {
            "ok": False, "skipped": False, "reason": "IP 解析失败",
            "ip": target_ip,
        }

    # ── 阶段 3：再次短会话写 city ──
    new_city = geo.city[:50]
    with SessionLocal() as db:
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            user.city = new_city
            db.commit()
    return {
        "ok": True, "skipped": False, "city": new_city,
        "province_code": geo.province_code, "province_name": geo.province_name,
        "country_code": geo.country_code, "source": geo.source,
    }


@router.get("/from-pref", summary="读取用户当前已配置的 city / province 偏好")
def from_pref(user_id: str = "", db: Session = Depends(get_db)):
    """返回用户当前已配置的城市信息。"""
    user_id = (user_id or "").strip()
    if not user_id:
        raise HTTPException(400, "user_id 不能为空")
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "user_id": user_id,
        "city": user.city or "",
        "province_code": "",  # 暂未单独存 province；解析时由 IP 实时算
        "province_name": "",
    }


@router.get("/health", summary="IP 地理服务健康检查")
def health():
    """返回缓存大小、配置状态，供管理后台巡检。"""
    from app.domains.platform.services.ip_geolocation import (
        cache_size, _bdc_api_key, _ipinfo_token,
    )
    return {
        "ok": True,
        "cache_size": cache_size(),
        "bdc_key_configured": bool(_bdc_api_key()),
        "ipinfo_token_configured": bool(_ipinfo_token()),
    }


__all__ = ["router"]
