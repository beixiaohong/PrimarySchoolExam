"""教材版本配置（后台配置，每年级每科目可配多个版本）与用户选择（047 迁移建表）

- TextbookVersion：后台配置的教材版本（如 人教版/北师大版/外研版），按 学科+年级 独立；
  用户未选择时默认取 sort_order 最小（其次 id 最小）的启用版本。
- UserTextbookPref：用户每学科选择的版本（默认不填，查询时回退默认版本）。
- word_books.textbook_id（047 迁移加列）：词书归属版本；新学选材按用户版本过滤，
  累计统计（career）不过滤，切换版本不丢历史学习量。
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Integer, String,
                        UniqueConstraint)

from ..database import Base


class TextbookVersion(Base):
    """教材版本（后台配置）"""
    __tablename__ = "textbook_versions"
    __table_args__ = {"comment": "教材版本：后台配置，按学科+年级独立，用户端默认取 sort_order 最小"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    subject = Column(String(20), nullable=False, index=True, comment="学科：数学/语文/英语")
    grade = Column(Integer, nullable=False, index=True, comment="年级 1-9")
    name = Column(String(50), nullable=False, comment="版本名，如 人教版/北师大版/外研版")
    sort_order = Column(Integer, default=0, comment="排序权重（小在前，默认选最小）")
    enabled = Column(Boolean, default=True, comment="是否启用")
    region = Column(String(8), nullable=False, default="",
                    comment="省份代码（chinaAdminCode 前 2 位，如 11=北京 31=上海；空=全国通用）")
    remark = Column(String(200), default="", comment="备注")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")


class UserTextbookPref(Base):
    """用户每学科教材版本选择"""
    __tablename__ = "user_textbook_prefs"
    __table_args__ = (
        UniqueConstraint("user_id", "subject", name="uq_user_subject_textbook"),
        {"comment": "用户教材版本选择：每用户每学科一个版本，未配置回退默认版本"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    subject = Column(String(20), nullable=False, comment="学科")
    textbook_id = Column(Integer, nullable=False, comment="教材版本 id（textbook_versions.id）")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


__all__ = ["TextbookVersion", "UserTextbookPref"]
