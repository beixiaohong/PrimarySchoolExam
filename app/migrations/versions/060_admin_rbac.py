"""060 - 后台 RBAC（复用 admins.role 枚举，新增权限目录与角色映射，admins 补 status）

基线策略：MySQL-only，幂等。
- 复用现有 admins.role 枚举（admin/super/ops），不新增 role_id 外键；
- admin_permissions / admin_role_permissions 两张表由 app.models.admin 的 ORM 模型经
  init_db 的 create_all 建表（生产亦如此），本迁移仅做种子数据；
- admins 表补 status 列（启用/停用），幂等 ALTER（MySQL DDL 自动提交，重复列异常忽略）；
- 种子：写入权限点目录 + 角色默认权限映射（super=全部，admin=运营子集，ops=只读）。

RBAC 严格模式见 app.config.RBAC_STRICT（默认 false，灰度放行存量后台）。
"""
import logging

from sqlalchemy import text

from app.core.permissions import seed_rbac

logger = logging.getLogger("migrations")


def upgrade(db):
    # 1) admins.status 幂等补列（MySQL DDL 自动提交；重复列异常忽略）
    try:
        db.execute(text(
            "ALTER TABLE admins ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active'"
        ))
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # 2) 种子权限目录与角色映射（表由 create_all 建好）
    seed_rbac(db)
    db.commit()
    logger.info("060 RBAC 权限目录与角色映射已就绪")
