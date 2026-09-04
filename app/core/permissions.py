"""后台 RBAC 依赖与权限目录（S1 权限基座）。

设计要点（与 07-技术实施方案 §3.2.8 / §5.3 对齐）：
- 复用现有 admins.role 枚举（admin/super/ops），不新增 role_id 外键；
- 权限目录 admin_permissions + 角色映射 admin_role_permissions 由迁移 060 建表并种子；
- require_perm 组合「后台登录鉴权 + 权限点校验」；RBAC_STRICT=false 时仅做登录鉴权（灰度放行）；
- 默认 RBAC_STRICT=false：存量管理员与既有后台调用不受影响，开启严格模式后再收紧。

import-linter 备注：本模块属 app.core（横切基础设施），不在九域独立性契约监控范围；
其引用 app.routers.admin.common 的 _require_admin/_audit 为共享后台鉴权辅助，不构成域间耦合。
"""
import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import RBAC_STRICT
from app.database import get_db
from app.models.admin import Admin, AdminPermission, AdminRolePermission, AdminOperationLog
from app.core.auth import _require_admin

logger = logging.getLogger(__name__)

# 权限点目录：code / 名称 / 分组 / 是否高危（高危=强制审计+可配审批）
PERMISSIONS = [
    {"code": "content:manage", "name": "内容管理", "group": "内容", "is_high_risk": False},
    {"code": "content:review", "name": "内容审核", "group": "内容", "is_high_risk": False},
    {"code": "content:view", "name": "内容查看", "group": "内容", "is_high_risk": False},
    {"code": "content:annotate", "name": "知识点标注", "group": "内容", "is_high_risk": False},
    {"code": "knowledge:manage", "name": "知识点管理", "group": "内容", "is_high_risk": False},
    {"code": "user:manage", "name": "用户管理", "group": "用户", "is_high_risk": False},
    {"code": "user:ban", "name": "用户封禁", "group": "用户", "is_high_risk": True},
    {"code": "benefit:grant_manual", "name": "手动发放资产/权益", "group": "权益", "is_high_risk": True},
    {"code": "benefit:vip_manage", "name": "VIP 管理", "group": "权益", "is_high_risk": True},
    {"code": "benefit:grant", "name": "权益发放", "group": "权益", "is_high_risk": True},
    {"code": "finance:refund", "name": "退款", "group": "财务", "is_high_risk": True},
    {"code": "payment_account:manage", "name": "收款账户管理", "group": "财务", "is_high_risk": True},
    {"code": "order:confirm_payment", "name": "订单支付确认", "group": "订单", "is_high_risk": True},
    {"code": "order:approve", "name": "大额订单审批", "group": "订单", "is_high_risk": True},
    {"code": "order:refund", "name": "订单退款", "group": "订单", "is_high_risk": True},
    {"code": "order:reverse", "name": "订单冲正", "group": "订单", "is_high_risk": True},
    {"code": "order:view_all", "name": "订单全量查看", "group": "订单", "is_high_risk": False},
    {"code": "product:view", "name": "商品查看", "group": "商品", "is_high_risk": False},
    {"code": "product:manage", "name": "商品管理", "group": "商品", "is_high_risk": True},
    {"code": "audit:view", "name": "审计查看", "group": "审计", "is_high_risk": False},
    {"code": "audit:export", "name": "审计导出", "group": "审计", "is_high_risk": False},
    {"code": "config:manage", "name": "系统配置管理", "group": "配置", "is_high_risk": False},
    {"code": "rbac:manage", "name": "角色权限管理", "group": "权限", "is_high_risk": True},
    {"code": "dashboard:view", "name": "数据看板查看", "group": "数据", "is_high_risk": False},
    {"code": "analytics:view", "name": "运营分析查看", "group": "数据", "is_high_risk": False},
    {"code": "mastery:recompute", "name": "掌握度重算触发", "group": "数据", "is_high_risk": False},
    {"code": "mastery:view_all", "name": "掌握度全量查看", "group": "数据", "is_high_risk": False},
]

# 角色默认权限映射（直接复用 admins.role 现有枚举值）
ROLE_PERMISSIONS = {
    # 超级管理员拥有全部权限点
    "super": [p["code"] for p in PERMISSIONS],
    # 普通管理员：运营子集（内容/用户/权益发放/审计查看/配置/看板），无财务/订单/权限管理
    "admin": [
        "content:manage", "content:review", "content:view", "content:annotate", "knowledge:manage",
        "user:manage", "benefit:grant_manual", "benefit:vip_manage", "benefit:grant",
        "audit:view", "config:manage", "dashboard:view", "analytics:view",
        "mastery:recompute", "mastery:view_all",
    ],
    # 运维：只读
    "ops": ["dashboard:view", "analytics:view", "audit:view"],
}


def has_perm(role: str, code: str) -> bool:
    """判断角色是否拥有某权限点（super 恒为真）。"""
    if role == "super":
        return True
    return code in ROLE_PERMISSIONS.get(role, [])


def require_perm(code: str, *, audit_action: str | None = None, high_risk: bool = False,
                  audit_target_type: str = "", audit_amount_fen: int | None = None,
                  audit_extra: str = ""):
    """后台权限依赖工厂：组合登录鉴权 + 权限点校验（+ 可选审计）。

    参数：
        code：所需权限点，如 "benefit:grant_manual"。
        audit_action：非空时在放行后补一条操作审计（高危操作建议传）。
        high_risk：仅作文档标注，实际高危约束由权限点目录 is_high_risk 驱动。
        audit_target_type：审计对象类型（user/config/asset/vip/order/permission...）。
        audit_amount_fen：审计涉及金额（分），无则 None。
        audit_extra：审计扩展上下文 JSON 字符串。
    行为：
        RBAC_STRICT=false（默认，灰度期）：仅做登录鉴权，跳过权限点校验，避免影响存量后台；
        RBAC_STRICT=true：无权限返回 403。
    """

    def _dep(admin: Admin = Depends(_require_admin),
             db: Session = Depends(get_db),
             request: Request = None) -> Admin:
        if not RBAC_STRICT:
            return admin
        if not has_perm(admin.role, code):
            raise HTTPException(403, f"无权限：{code}")
        if audit_action:
            ip = request.client.host if request and request.client else ""
            ua = request.headers.get("user-agent", "") if request else ""
            db.add(AdminOperationLog(
                admin=admin.username, action=audit_action, target="",
                detail=f"权限点:{code}",
                ip=ip, user_agent=ua, amount_fen=audit_amount_fen,
                target_type=audit_target_type, extra_json=audit_extra))
            db.commit()
        return admin

    return _dep


def seed_rbac(db: Session) -> None:
    """幂等种子：写入权限点目录 + 角色默认映射（迁移 060 调用）。"""
    existing = {row.code for row in db.query(AdminPermission.code).all()}
    for p in PERMISSIONS:
        if p["code"] not in existing:
            db.add(AdminPermission(
                code=p["code"], name=p["name"], group_name=p["group"],
                is_high_risk=1 if p["is_high_risk"] else 0,
            ))
    db.flush()
    existing_rp = {
        (row.role, row.permission_code)
        for row in db.query(AdminRolePermission.role, AdminRolePermission.permission_code).all()
    }
    for role, codes in ROLE_PERMISSIONS.items():
        for code in codes:
            if (role, code) not in existing_rp:
                db.add(AdminRolePermission(role=role, permission_code=code))
    db.flush()
