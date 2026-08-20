"""网课（在线课程）模型：系统配置 + 家长单独配置（048 迁移建表）

- source=system：后台（系统）配置的网课，所有用户可见（按学科/年级过滤）
- source=parent：家长为孩子单独配置的网课（parent_uid 记录创建者账号）
- grade=0 表示不限年级；subject="" 表示不限学科
- 视频以 URL 形式提供（支持 b站/腾讯视频/直链 mp4 等），不做文件上传
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Integer, String, Text)

from ..database import Base


class OnlineCourse(Base):
    """网课（系统配置或家长自定义）"""
    __tablename__ = "online_courses"
    __table_args__ = {"comment": "网课：系统配置默认展示，家长可单独添加；视频 URL 形式"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    subject = Column(String(20), default="", index=True, comment="学科（空=不限）")
    grade = Column(Integer, default=0, index=True, comment="年级（0=不限）")
    title = Column(String(100), nullable=False, comment="课程标题")
    description = Column(Text, default="", comment="课程简介")
    cover_url = Column(String(500), default="", comment="封面图 URL（可选）")
    video_url = Column(String(500), default="", comment="视频 URL（b站/腾讯/直链 mp4）")
    duration_min = Column(Integer, default=0, comment="时长（分钟，0=未知）")
    source = Column(String(20), default="system", comment="system=系统配置 / parent=家长配置")
    parent_uid = Column(String(50), nullable=True, index=True, comment="家长配置时的创建者账号（source=parent）")
    enabled = Column(Boolean, default=True, comment="是否启用")
    sort_order = Column(Integer, default=0, comment="排序（小在前）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


__all__ = ["OnlineCourse"]
