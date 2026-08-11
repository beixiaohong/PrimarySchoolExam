"""初中九科扩展模型：六科题库与教学进度

题库为种子版数据（033 迁移播种），后续可由管理端人工扩充。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from ..database import Base


class MiddleQuestion(Base):
    """初中六科选择题题库（物理/化学/生物/道德与法治/历史/地理）"""
    __tablename__ = "middle_questions"
    __table_args__ = {"comment": "初中六科选择题题库：种子版，需人工校对扩充"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    subject = Column(String(20), nullable=False, index=True, comment="学科：物理/化学/生物/道德与法治/历史/地理")
    grade = Column(Integer, default=7, comment="适用年级 7-9")
    type = Column(String(50), default="choice", comment="题型编码，目前均为 choice 选择题")
    question = Column(Text, nullable=False, comment="题干")
    options_json = Column(Text, default="[]", comment="选项 JSON 数组")
    answer = Column(String(200), nullable=False, comment="正确答案（选项文本）")
    analysis = Column(Text, default="", comment="答案解析")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<MiddleQuestion {self.subject} G{self.grade}: {self.question[:20]}>"


class TeachingProgress(Base):
    """教学进度：每科当前书/单元（家长维护，驱动背诵与出卷的课堂同步）"""
    __tablename__ = "teaching_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "subject", name="uq_progress_user_subject"),
        {"comment": "教学进度：每用户每科一条，记录当前词书与单元"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户 ID")
    subject = Column(String(20), nullable=False, comment="学科")
    book_id = Column(Integer, nullable=True, comment="英语词书 ID（其他学科可空）")
    chapter = Column(String(100), default="", comment="当前章节/单元，如 Unit 3")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<TeachingProgress {self.user_id} {self.subject} {self.chapter}>"
