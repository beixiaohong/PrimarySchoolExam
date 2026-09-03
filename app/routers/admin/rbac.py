"""管理后台 RBAC 接口（S1-B9 / 07-技术实施方案 §4.5）

路由清单（均挂 /api/admin 前缀，统一 require_perm 鉴权 + 审计落库）：
- GET  /rbac/roles            列出全部角色及其权限集
- PUT  /rbac/roles/{role}     整体设置某角色的权限集（含 BR-PERM-04 互斥校验）
- GET  /rbac/permissions      权限点目录（按分组）
- POST /rbac/roles/{role}/permissions  为角色增删单个权限（含互斥校验）
- POST /rbac/admins/{admin_id}/role    为管理员分配角色（含互斥约束）

全部经 app.domains.platform.contracts 触达 D8 rbac 服务（import-linter 合规）。
RBAC_STRICT=false（默认灰度）时仅做登录鉴权，不影响存量后台。
"""
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.permissions import require_perm
from app.domains.platform.contracts import (
    rbac_list_roles,
    rbac_get_permissions,
    rbac_set_role_permissions,
    rbac_add_role_permission,
    rbac_remove_role_permission,
    rbac_assign_admin_role,
)
from . import router
from .common import _audit


class RolePermsReq(BaseModel):
    """整体设置角色权限集：权限码列表。"""
    permissions: list[str]


class RolePermOpReq(BaseModel):
    """角色单权限增删：权限码 + 操作（add/remove）。"""
    code: str
    op: str = "add"  # add | remove


class AdminRoleReq(BaseModel):
    """管理员角色分配：目标角色名。"""
    role: str


def _req_meta(request: Request | None):
    """从请求抽取审计所需来源信息（IP/UA）。"""
    ip = request.client.host if request and request.client else ""
    ua = request.headers.get("user-agent", "") if request else ""
    return ip, ua


@router.get("/rbac/roles", summary="列出全部角色及其权限集")
def api_list_roles(db: Session = Depends(get_db),
                   admin=Depends(require_perm("rbac:manage"))):
    """返回 super/admin/ops 三个角色当前拥有的权限点。"""
    return rbac_list_roles(db)


@router.get("/rbac/permissions", summary="权限点目录")
def api_permissions(db: Session = Depends(get_db),
                    admin=Depends(require_perm("rbac:manage"))):
    """返回全部权限点（含分组与是否高危），供角色编辑页展示。"""
    return rbac_get_permissions(db)


@router.put("/rbac/roles/{role}", summary="整体设置某角色的权限集")
def api_set_role(role: str, req: RolePermsReq, db: Session = Depends(get_db),
                 admin=Depends(require_perm("rbac:manage")), request: Request = None):
    """整体覆盖某角色的权限集；命中 BR-PERM-04 互斥或非法权限点返回 400。"""
    try:
        perms = rbac_set_role_permissions(db, role, req.permissions)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    ip, ua = _req_meta(request)
    _audit(db, admin, action="rbac:set_role", target=role,
           detail=f"权限集={req.permissions}", ip=ip, user_agent=ua,
           target_type="permission", extra_json=f'{{"role":"{role}"}}')
    return {"role": role, "permissions": perms}


@router.post("/rbac/roles/{role}/permissions", summary="为角色增删单个权限（含互斥校验）")
def api_role_perm(role: str, req: RolePermOpReq, db: Session = Depends(get_db),
                  admin=Depends(require_perm("rbac:manage")), request: Request = None):
    """向角色追加或移除单个权限；命中互斥返回 400。"""
    try:
        if req.op == "remove":
            perms = rbac_remove_role_permission(db, role, req.code)
        else:
            perms = rbac_add_role_permission(db, role, req.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    ip, ua = _req_meta(request)
    _audit(db, admin, action="rbac:role_perm", target=role,
           detail=f"{req.op}:{req.code}", ip=ip, user_agent=ua,
           target_type="permission", extra_json=f'{{"role":"{role}","code":"{req.code}","op":"{req.op}"}}')
    return {"role": role, "permissions": perms}


@router.post("/rbac/admins/{admin_id}/role", summary="为管理员分配角色（含互斥约束）")
def api_assign_admin(admin_id: int, req: AdminRoleReq, db: Session = Depends(get_db),
                     admin=Depends(require_perm("rbac:manage")), request: Request = None):
    """为指定管理员设置角色（写 admins.role）；角色非法返回 400。"""
    try:
        a = rbac_assign_admin_role(db, admin_id, req.role)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    ip, ua = _req_meta(request)
    _audit(db, admin, action="rbac:assign_admin", target=str(admin_id),
           detail=f"role={req.role}", ip=ip, user_agent=ua,
           target_type="permission", extra_json=f'{{"admin_id":{admin_id},"role":"{req.role}"}}')
    return {"id": a.id, "username": a.username, "role": a.role}
