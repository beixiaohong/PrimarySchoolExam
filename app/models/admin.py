"""管理后台模型：管理员、操作审计日志、系统配置"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from ..database import Base


class Admin(Base):
    """管理员账号（token 会话制：登录发 token，存库校验）"""
    __tablename__ = "admins"
    __table_args__ = {"comment": "管理员账号：token 会话制，登录发 token 存库校验"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    username = Column(String(50), nullable=False, unique=True, index=True, comment="管理员用户名")
    password_hash = Column(String(128), nullable=False, comment="密码 pbkdf2 哈希")
    # role 枚举取值：admin=普通管理员，super=超级管理员（最高权限），ops=运维人员
    role = Column(String(20), nullable=False, default="admin",
                  comment="admin/super/ops")
    token = Column(String(64), nullable=True, index=True, comment="当前会话 token")
    token_expires_at = Column(DateTime, nullable=True, comment="token 过期时间")
    last_login_at = Column(DateTime, nullable=True, comment="最近登录时间")
    # status：账号启用状态（RBAC 迁移 060 补列）：active=启用 / disabled=停用
    # server_default 保证 create_all 重建测试库时列自带默认值，避免 ORM 未显式赋值时 1364 报错
    # （迁移 060 的 ALTER 亦带 DEFAULT，二者并存无害：create_all 已建列时 ALTER 静默跳过）。
    status = Column(String(16), nullable=False, default="active", server_default="active",
                    comment="active/disabled")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class AdminOperationLog(Base):
    """管理员操作审计日志（账号处理/资产调整/VIP/配置变更全部落库）"""
    __tablename__ = "admin_operation_logs"
    __table_args__ = {"comment": "管理员操作审计日志：账号/资产/VIP/配置变更全部落库"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    admin = Column(String(50), nullable=False, index=True, comment="操作管理员")
    action = Column(String(50), nullable=False, comment="操作类型")
    target = Column(String(64), nullable=False, default="", comment="操作对象（user_id/配置key）")
    detail = Column(Text, nullable=False, default="", comment="变更明细")
    created_at = Column(DateTime, default=datetime.now, comment="操作时间")
    # ── S1-B7 审计增强（迁移 070 补列，见 §3.2.9）──
    # TEXT 列无 DEFAULT（MySQL 1101），故 user_agent/extra_json 设为可空 + 客户端默认 ""；
    # 写入路径（_audit / require_perm）恒填 ""，实际不会落 NULL。
    ip = Column(String(64), nullable=False, default="", comment="操作来源 IP")
    user_agent = Column(Text, nullable=True, default="", comment="操作来源 UA")
    amount_fen = Column(Integer, nullable=True, comment="涉及金额（分），无则空")
    target_type = Column(String(32), nullable=False, default="",
                         comment="操作对象类型：user/config/asset/vip/order/permission/...")
    extra_json = Column(Text, nullable=True, default="", comment="扩展信息 JSON（操作上下文）")


class SystemConfig(Base):
    """系统配置（三方 API 密钥等，优先级高于 .env）"""
    __tablename__ = "system_config"
    __table_args__ = {"comment": "系统配置：三方 API 密钥等，优先级高于 .env"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    key = Column(String(80), nullable=False, unique=True, index=True, comment="配置项名称")
    value = Column(Text, nullable=False, default="", comment="配置值")
    updated_by = Column(String(50), nullable=False, default="", comment="最后修改人")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="最后修改时间")


class AdminPermission(Base):
    """后台权限点目录（RBAC 迁移 060 新增；create_all 建表，迁移种子写入）。"""
    __tablename__ = "admin_permissions"
    __table_args__ = {"comment": "后台权限点目录"}
    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    code = Column(String(64), nullable=False, unique=True, index=True, comment="权限点编码，如 benefit:grant_manual")
    name = Column(String(128), nullable=False, comment="权限点中文名")
    group_name = Column(String(64), nullable=False, default="", comment="分组（内容/用户/权益/财务/订单/审计/配置/权限/数据）")
    is_high_risk = Column(Integer, nullable=False, default=0, comment="是否高危操作（强制审计+可配审批）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class AdminRolePermission(Base):
    """后台角色→权限映射（直接复用 admins.role 枚举：super/admin/ops）。"""
    __tablename__ = "admin_role_permissions"
    __table_args__ = (
        UniqueConstraint("role", "permission_code", name="uq_rp_role_perm"),
        {"comment": "角色→权限映射（复用 admins.role 枚举）"},
    )
    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    role = Column(String(20), nullable=False, index=True, comment="复用 admins.role：super/admin/ops")
    permission_code = Column(String(64), nullable=False, index=True, comment="admin_permissions.code")
