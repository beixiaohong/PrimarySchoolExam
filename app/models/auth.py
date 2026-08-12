"""验证码模型（026_user_auth 建表）

用途：注册/绑定/重置密码的邮箱与短信验证码。
code 只存哈希，5 分钟有效，校验失败 5 次作废，消费后 used=True。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..database import Base


class AuthCode(Base):
    """验证码记录"""
    __tablename__ = "auth_codes"
    __table_args__ = {"comment": "验证码：注册/绑定/重置密码的邮箱短信验证码，只存哈希"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    # purpose 取值：register=注册，bind=绑定账号，reset=重置密码
    purpose = Column(String(20), nullable=False, comment="用途：register/bind/reset")
    target = Column(String(120), nullable=False, index=True, comment="目标邮箱/手机号")
    code_hash = Column(String(128), nullable=False, comment="验证码 SHA256 哈希")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    used = Column(Boolean, default=False, nullable=False, comment="是否已消费")
    fail_count = Column(Integer, default=0, nullable=False, comment="连续校验失败次数")
    created_at = Column(DateTime, default=datetime.now, comment="发送时间（用于频控）")
