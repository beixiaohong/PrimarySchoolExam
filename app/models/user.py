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

    id = Column(Integer, primary_key=True, autoincrement=True)
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

    user_id = Column(String(50), primary_key=True)
    note = Column(String(100), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now)
