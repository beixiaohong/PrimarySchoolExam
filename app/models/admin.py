"""管理后台模型：管理员、操作审计日志、系统配置"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from ..database import Base


class Admin(Base):
    """管理员账号（token 会话制：登录发 token，存库校验）"""
    __tablename__ = "admins"
    __table_args__ = {"comment": "管理员账号：token 会话制，登录发 token 存库校验"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    username = Column(String(50), nullable=False, unique=True, index=True, comment="管理员用户名")
    password_hash = Column(String(128), nullable=False, comment="密码 pbkdf2 哈希")
    role = Column(String(20), nullable=False, default="admin",
                  comment="admin/super/ops")
    token = Column(String(64), nullable=True, index=True, comment="当前会话 token")
    token_expires_at = Column(DateTime, nullable=True, comment="token 过期时间")
    last_login_at = Column(DateTime, nullable=True, comment="最近登录时间")
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


class SystemConfig(Base):
    """系统配置（三方 API 密钥等，优先级高于 .env）"""
    __tablename__ = "system_config"
    __table_args__ = {"comment": "系统配置：三方 API 密钥等，优先级高于 .env"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    key = Column(String(80), nullable=False, unique=True, index=True, comment="配置项名称")
    value = Column(Text, nullable=False, default="", comment="配置值")
    updated_by = Column(String(50), nullable=False, default="", comment="最后修改人")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="最后修改时间")
