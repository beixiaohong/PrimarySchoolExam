"""系统公告 / 站内信模型

公告由管理员在后台发布，面向全体学生/家长；学生端通过 /api/announcements 拉取。
用户与管理员的实时沟通由 IM 模块承载（学生可发起与管理员的私聊），公告本身作为
「站内信 / 通知中心」呈现，不强制塞入 IM 聊天流，避免对全体用户广播建聊的写放大。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..database import Base


class Announcement(Base):
    """系统公告"""
    __tablename__ = "admin_announcements"
    __table_args__ = {"comment": "系统公告/站内信：管理后台发布，学生端通知中心拉取"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    title = Column(String(200), nullable=False, comment="公告标题")
    content = Column(Text, nullable=False, comment="公告正文")
    target_type = Column(String(20), default="all", comment="受众：all=全部/grade=按年级/user=指定用户")
    target_value = Column(String(50), nullable=True, comment="target_type=grade 时为年级数字；=user 时为 user_id")
    is_pinned = Column(Boolean, default=False, comment="是否置顶")
    created_by = Column(String(50), nullable=False, comment="发布人(管理员账号)")
    created_at = Column(DateTime, default=datetime.now, comment="发布时间")
