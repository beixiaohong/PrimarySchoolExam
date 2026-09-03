"""D8 平台域 RBAC 角色分配服务（S1-B8 / 07-技术实施方案 §3.2.8 / §4.5）

职责：角色→权限集的查询与变更，以及管理员角色分配；强制 BR-PERM-04 互斥校验。
复用 admins.role 枚举（super/admin/ops）+ admin_permissions / admin_role_permissions 表。

本服务经 app.domains.platform.contracts 暴露给后台路由（import-linter：admin 域只能经
contracts 触达域实现），不直接引用 app.routers.admin 内部。

约定（持连铁律）：所有函数只做数据库读写，不发起外部阻塞调用；事务由路由层控制
（变更类函数在落库前 flush、由调用方统一 commit，避免长事务占连接池）。
"""
import logging

from sqlalchemy.orm import Session

from app.models.admin import Admin, AdminPermission, AdminRolePermission

logger = logging.getLogger(__name__)

# 复用的角色枚举（与 admins.role 一致）
VALID_ROLES = ("super", "admin", "ops")

# BR-PERM-04：互斥权限对 —— 不可同授一个角色
# （订单支付确认 与 收款账户管理 互斥：防止同一角色既确认收款又管理收款账户）
MUTEX_PERMISSION_PAIRS = [
    ("order:confirm_payment", "payment_account:manage"),
]

# 互斥冲突业务码（路由层据此转 400）
ERR_MUTEX = "PERMISSION_MUTEX"


def _valid_codes(db: Session) -> set:
    """返回当前权限点目录中所有合法 code。"""
    return {row.code for row in db.query(AdminPermission.code).all()}


def check_mutex(codes) -> tuple | None:
    """检查权限集合是否命中互斥对。

    返回冲突的互斥对 (a, b)，无冲突返回 None。codes 为该角色即将拥有的权限集合。
    """
    codes = set(codes)
    for a, b in MUTEX_PERMISSION_PAIRS:
        if a in codes and b in codes:
            return (a, b)
    return None


def get_permissions_catalog(db: Session) -> list:
    """权限点目录（按分组聚合，供角色编辑页展示）。"""
    rows = (db.query(AdminPermission)
            .order_by(AdminPermission.group_name, AdminPermission.code).all())
    return [
        {"code": r.code, "name": r.name, "group_name": r.group_name,
         "is_high_risk": bool(r.is_high_risk)}
        for r in rows
    ]


def list_roles(db: Session) -> list:
    """列出全部角色及其当前权限集。"""
    rows = db.query(AdminRolePermission).all()
    by_role: dict = {role: [] for role in VALID_ROLES}
    for r in rows:
        by_role.setdefault(r.role, []).append(r.permission_code)
    return [
        {"role": role, "permissions": sorted(by_role.get(role, []))}
        for role in VALID_ROLES
    ]


def _assert_role(role: str):
    if role not in VALID_ROLES:
        raise ValueError(f"未知角色：{role}（合法值：{', '.join(VALID_ROLES)}）")


def set_role_permissions(db: Session, role: str, codes: list) -> list:
    """整体替换某角色的权限集（先互斥校验 + 合法性校验，再落库）。

    返回该角色更新后的权限码列表（已排序）。互斥或非法抛 ValueError。
    """
    _assert_role(role)
    codes = sorted(set(codes))
    valid = _valid_codes(db)
    unknown = [c for c in codes if c not in valid]
    if unknown:
        raise ValueError(f"未知权限点：{', '.join(unknown)}")
    conflict = check_mutex(codes)
    if conflict:
        raise ValueError(
            f"{ERR_MUTEX}: 权限点 {conflict[0]} 与 {conflict[1]} 互斥，不可同授角色 {role}")
    # 删旧 + 插新（整体覆盖）
    db.query(AdminRolePermission).filter(AdminRolePermission.role == role).delete()
    for c in codes:
        db.add(AdminRolePermission(role=role, permission_code=c))
    db.flush()
    return codes


def add_role_permission(db: Session, role: str, code: str) -> list:
    """向角色追加一个权限（带互斥校验）。返回更新后的权限码列表。"""
    _assert_role(role)
    valid = _valid_codes(db)
    if code not in valid:
        raise ValueError(f"未知权限点：{code}")
    existing = {r.permission_code for r in
                db.query(AdminRolePermission)
                .filter(AdminRolePermission.role == role).all()}
    if code in existing:
        return sorted(existing)
    candidate = existing | {code}
    conflict = check_mutex(candidate)
    if conflict:
        raise ValueError(
            f"{ERR_MUTEX}: 权限点 {conflict[0]} 与 {conflict[1]} 互斥，不可同授角色 {role}")
    db.add(AdminRolePermission(role=role, permission_code=code))
    db.flush()
    return sorted(candidate)


def remove_role_permission(db: Session, role: str, code: str) -> list:
    """从角色移除一个权限。返回剩余权限码列表。"""
    _assert_role(role)
    db.query(AdminRolePermission).filter(
        AdminRolePermission.role == role,
        AdminRolePermission.permission_code == code,
    ).delete()
    db.flush()
    remaining = {r.permission_code for r in
                 db.query(AdminRolePermission)
                 .filter(AdminRolePermission.role == role).all()}
    return sorted(remaining)


def assign_admin_role(db: Session, admin_id: int, role: str) -> Admin:
    """为管理员分配角色（写 admins.role）。

    互斥约束作用于「角色权限集」而非个人，此处仅校验角色合法 + 账号存在。
    """
    _assert_role(role)
    admin = db.query(Admin).filter(Admin.id == admin_id).first()
    if admin is None:
        raise ValueError(f"管理员不存在：id={admin_id}")
    admin.role = role
    db.flush()
    return admin
