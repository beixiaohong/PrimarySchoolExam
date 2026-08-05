"""古诗文/文言文数据模型"""
from datetime import datetime, date
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Text, Date, UniqueConstraint

from ..database import Base


class ClassicalText(Base):
    """古诗文/文言文篇目"""
    __tablename__ = "classical_texts"
    __table_args__ = (
        UniqueConstraint("title", name="uq_text_title"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, comment="篇名")
    author = Column(String(100), default="", comment="作者")
    dynasty = Column(String(50), default="", comment="朝代")
    text_type = Column(String(20), default="poem", comment="poem=古诗, prose=文言文/古文")
    grade = Column(Integer, default=3, comment="适用年级 1-9")
    content = Column(Text, nullable=False, comment="全文，行用\\n分隔")
    lines_json = Column(Text, default="[]", comment="分行JSON数组，用于出题")
    tags = Column(String(200), default="", comment="标签，逗号分隔")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ClassicalText {self.title} - {self.author}>"


class ClassicalProgress(Base):
    """用户对古诗文的学习/背诵进度（同样基于艾宾浩斯曲线）"""
    __tablename__ = "classical_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "text_id", name="uq_user_classical"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    text_id = Column(Integer, nullable=False, comment="FK to classical_texts.id")

    status = Column(String(20), default="learning", comment="learning/mastered")
    review_stage = Column(Integer, default=0, comment="0~5 对应6个间隔")
    next_review_date = Column(Date, nullable=True)
    last_review_date = Column(Date, nullable=True)
    first_learn_date = Column(Date, nullable=True)

    correct_count = Column(Integer, default=0)
    wrong_count = Column(Integer, default=0)
    total_reviews = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ClassicalDailyLog(Base):
    """古诗文每日学习日志"""
    __tablename__ = "classical_daily_log"
    __table_args__ = (
        UniqueConstraint("user_id", "learn_date", name="uq_user_classical_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    learn_date = Column(Date, nullable=False)
    texts_learned = Column(Integer, default=0, comment="当天新学篇数")
    texts_reviewed = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    wrong_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
