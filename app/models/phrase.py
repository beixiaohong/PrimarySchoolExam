"""英语词组和句子数据模型"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint

from ..database import Base


class Phrase(Base):
    """词组"""
    __tablename__ = "phrases"
    __table_args__ = (
        UniqueConstraint("phrase", name="uq_phrase"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    grade = Column(Integer, nullable=False, comment="适用年级 3-6")
    phrase = Column(String(200), nullable=False, comment="英文词组")
    meaning = Column(String(200), nullable=False, comment="中文释义")
    type = Column(String(50), default="动词词组", comment="类型：动词词组/介词词组/疑问词组等")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Phrase {self.phrase} - {self.meaning}>"


class Sentence(Base):
    """句子"""
    __tablename__ = "sentences"
    __table_args__ = (
        UniqueConstraint("sentence_en", name="uq_sentence_en"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    grade = Column(Integer, nullable=False, comment="适用年级 3-6")
    sentence_en = Column(String(500), nullable=False, comment="英文句子")
    sentence_cn = Column(String(500), nullable=False, comment="中文翻译")
    type = Column(String(50), default="", comment="句子类型：问候/特殊疑问句/比较等")
    grammar_point = Column(String(100), default="", comment="语法点")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Sentence {self.sentence_en[:30]}>"
