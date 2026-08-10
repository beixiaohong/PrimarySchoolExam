"""用户模型

支持三种注册方式：邮箱验证码 / 手机验证码 / 昵称快捷（存量账号）。
user_id 仍为全局业务主键标识；认证相关字段由 026_user_auth 迁移补齐。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, Integer, String, DateTime, Date

from ..database import Base


class User(Base):
    """用户档案"""
    __tablename__ = "users"
    __table_args__ = {"comment": "用户档案：登录标识+年级学科偏好+认证信息（邮箱/手机/密码/昵称）"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, unique=True, index=True,
                     comment="用户名（学生姓名/学号）")

    # ── 常用设置 ──
    grade = Column(Integer, default=6, comment="常用年级 1-9")
    subject = Column(String(20), default="英语", comment="常用学科：数学/英语/语文")

    # ── 认证（026_user_auth） ──
    email = Column(String(120), nullable=True, unique=True, index=True, comment="绑定邮箱")
    phone = Column(String(20), nullable=True, unique=True, index=True, comment="绑定手机号")
    password_hash = Column(String(128), nullable=True, comment="登录密码哈希（pbkdf2）")
    nickname = Column(String(64), nullable=True, comment="昵称（昵称账号展示名）")
    auth_type = Column(String(10), nullable=True, comment="注册方式：email/phone/nickname")
    email_verified = Column(Boolean, default=False, comment="邮箱是否已验证")
    phone_verified = Column(Boolean, default=False, comment="手机号是否已验证")
    city = Column(String(50), nullable=True, comment="天气城市（首页天气卡）")

    # ── 时间 ──
    created_at = Column(DateTime, default=datetime.now, comment="首次使用时间")
    last_login_at = Column(DateTime, default=datetime.now, comment="最近活跃时间")
    last_login_date = Column(Date, nullable=True, comment="最近活跃日期（用于连续天数）")

    def __repr__(self):
        return f"<User {self.user_id} grade={self.grade}>"


class VipUser(Base):
    """VIP 名单（009 迁移建表，补模型供 MySQL 基线建表）：免费链失败后追加付费链"""
    __tablename__ = "vip_users"
    __table_args__ = {"comment": "VIP 用户名单：AI 免费额度用尽后仍可调用付费链"}

    user_id = Column(String(50), primary_key=True, comment="用户名（主键，与 users.user_id 对应）")
    note = Column(String(100), nullable=False, default="", comment="备注（开通原因/有效期说明）")
    created_at = Column(DateTime, default=datetime.now, comment="加入 VIP 时间")
