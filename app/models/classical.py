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
        {"comment": "古诗文/文言文篇目库：全文+分行JSON用于默写与填空出题"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    title = Column(String(200), nullable=False, comment="篇名")
    author = Column(String(100), default="", comment="作者")
    dynasty = Column(String(50), default="", comment="朝代")
    text_type = Column(String(20), default="poem", comment="poem=古诗, prose=文言文/古文")
    grade = Column(Integer, default=3, comment="适用年级 1-9")
    semester = Column(String(10), default="全", server_default="全", comment="适用学期：上/下/全（迁移 029 新增）")
    content = Column(Text, nullable=False, comment="全文，行用\\n分隔")
    lines_json = Column(Text, default="[]", comment="分行JSON数组，用于出题")
    tags = Column(String(200), default="", comment="标签，逗号分隔")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<ClassicalText {self.title} - {self.author}>"


class ClassicalProgress(Base):
    """用户对古诗文的学习/背诵进度（同样基于艾宾浩斯曲线）"""
    __tablename__ = "classical_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "text_id", name="uq_user_classical"),
        {"comment": "古诗文学习进度：每用户每篇目一条，艾宾浩斯曲线复习"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, comment="用户名")
    text_id = Column(Integer, nullable=False, comment="所属篇目 ID（classical_texts.id）")

    status = Column(String(20), default="learning", comment="learning/mastered")
    review_stage = Column(Integer, default=0, comment="复习阶段 0~5 对应6个间隔")
    next_review_date = Column(Date, nullable=True, comment="下次复习日期")
    last_review_date = Column(Date, nullable=True, comment="上次复习日期")
    first_learn_date = Column(Date, nullable=True, comment="首次学习日期")

    correct_count = Column(Integer, default=0, comment="累计答对次数")
    wrong_count = Column(Integer, default=0, comment="累计答错次数")
    total_reviews = Column(Integer, default=0, comment="累计复习次数")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class ClassicalDailyLog(Base):
    """古诗文每日学习日志"""
    __tablename__ = "classical_daily_log"
    __table_args__ = (
        UniqueConstraint("user_id", "learn_date", name="uq_user_classical_date"),
        {"comment": "古诗文每日学习日志：每用户每天一条，统计新学/复习与对错"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, comment="用户名")
    learn_date = Column(Date, nullable=False, comment="学习日期")
    texts_learned = Column(Integer, default=0, comment="当天新学篇数")
    texts_reviewed = Column(Integer, default=0, comment="当天复习篇数")
    correct_count = Column(Integer, default=0, comment="当天答对次数")
    wrong_count = Column(Integer, default=0, comment="当天答错次数")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
