"""系统配置读取服务：system_config 表 > .env > 默认值，60 秒内存缓存

供各服务层（AI/天气/邮件等）读取可被管理后台在线覆盖的配置项。
"""
import os
import time
import logging

logger = logging.getLogger(__name__)

_CACHE_TTL = 60  # 秒
_cache: dict = {}  # key -> (value, ts)


def get(key: str, default: str = "") -> str:
    """按 system_config 表 > 环境变量 > default 的顺序取值（60s 缓存）"""
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[1] < _CACHE_TTL:
        return hit[0]

    value = default
    try:
        from ..database import SessionLocal
        from ..models.admin import SystemConfig
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if row and row.value:
                value = row.value
            else:
                value = os.environ.get(key, default)
        finally:
            db.close()
    except Exception as e:  # 表不存在/DB 异常时降级为环境变量
        logger.warning("sysconfig 读取失败（key=%s）: %s", key, e)
        value = os.environ.get(key, default)

    _cache[key] = (value, now)
    return value


def invalidate(key: str = None):
    """配置变更后主动失效缓存（key 为空则清空全部）"""
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)
