"""管理后台：三方配置读写"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin, SystemConfig
from app.domains.platform.contracts import sysconfig

from . import router
from .common import CONFIG_GROUPS, SECRET_HINTS, _audit, _require_admin


class ConfigSaveReq(BaseModel):
    """三方配置保存请求：配置键与值。"""
    key: str
    value: str


def _mask(key: str, value: str) -> str:
    """密钥类配置脱敏（仅显示尾 4 位）"""
    if not value:
        return ""
    if any(h in key.upper() for h in SECRET_HINTS):
        return "****" + value[-4:] if len(value) > 4 else "****"
    return value


@router.get("/config", summary="三方配置列表（分组 + 脱敏）")
def list_config(db: Session = Depends(get_db), admin: Admin = Depends(_require_admin)):
    """列出全部可管理三方配置（按分组），值做脱敏处理并标注来源（database/env/unset）。

    参数：db / admin：依赖注入。
    返回：{"groups": [{"group", "items": [{"key","value","source","updated_by","updated_at"}]}]}。
    副作用：只读，不写库。
    """
    rows = {r.key: r for r in db.query(SystemConfig).all()}
    groups = []
    for group, keys in CONFIG_GROUPS.items():
        items = []
        for key in keys:
            row = rows.get(key)
            env_val = sysconfig.get(key, "")  # DB > .env
            items.append({
                "key": key,
                "value": _mask(key, env_val),
                "source": "database" if (row and row.value) else ("env" if env_val else "unset"),
                "updated_by": row.updated_by if row else "",
                "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M") if row and row.updated_at else "",
            })
        groups.append({"group": group, "items": items})
    return {"groups": groups}


@router.post("/config", summary="保存三方配置（写入 system_config，60s 内生效）")
def save_config(req: ConfigSaveReq, db: Session = Depends(get_db),
                admin: Admin = Depends(_require_admin)):
    """保存三方配置到 system_config（优先级高于 .env，保存后立即失效缓存），并落审计日志。

    参数：req：key、value。
    业务约束：key 必须在可管理清单 CONFIG_GROUPS 内，否则 400。
    副作用：写入/更新 SystemConfig、sysconfig.invalidate(key) 使缓存失效、记审计日志。
    返回：{"ok": true}。
    """
    key = req.key.strip()
    all_keys = {k for keys in CONFIG_GROUPS.values() for k in keys}
    if key not in all_keys:
        raise HTTPException(400, "配置项不在可管理清单内")
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    old = _mask(key, row.value) if row else ""
    if row:
        row.value, row.updated_by = req.value, admin.username
    else:
        row = SystemConfig(key=key, value=req.value, updated_by=admin.username)
        db.add(row)
    db.commit()
    sysconfig.invalidate(key)  # 保存后立即失效缓存，下次读取即生效
    _audit(db, admin, "config:set", key, f"{old or '（空）'} → {_mask(key, req.value)}")
    return {"ok": True}


__all__ = ["ConfigSaveReq", "_mask", "list_config", "save_config"]
