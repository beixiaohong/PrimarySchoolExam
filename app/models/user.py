"""用户模型（轻量版：填用户名即用，无注册/密码）

记录用户名、常用年级/学科、首次使用时间与最近活跃时间。
前端用 localStorage 记住用户名，登录时调用 POST /api/user/login 登记即可。
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Date

from ..database import Base


class User(Base):
    """用户档案（用户名即标识）"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, unique=True, index=True,
                     comment="用户名（学生姓名/学号）")

    # ── 常用设置 ──
    grade = Column(Integer, default=6, comment="常用年级 1-9")
    subject = Column(String(20), default="英语", comment="常用学科：数学/英语/语文")

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
