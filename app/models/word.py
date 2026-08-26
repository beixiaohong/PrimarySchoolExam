"""英语单词数据模型"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class WordBook(Base):
    """词库（按教材/年级分组）"""
    __tablename__ = "word_books"
    __table_args__ = {"comment": "英语词库：按教材版本/年级/学期分组"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    name = Column(String(100), nullable=False, comment="词库名称，如'人教版PEP三年级上'")
    grade = Column(Integer, nullable=False, comment="年级 1-6")
    semester = Column(String(10), default="上", comment="学期：上/下")
    publisher = Column(String(50), default="人教版PEP", comment="出版社/教材版本")
    word_count = Column(Integer, default=0, comment="单词数量（自动维护）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    textbook_id = Column(Integer, nullable=True,
                         comment="教材版本 id（textbook_versions.id，047 迁移加列）")

    # 双向一对多：删除词库时级联删除其下全部单词
    words = relationship("Word", back_populates="book", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WordBook {self.name}>"


class Word(Base):
    """单词"""
    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("book_id", "word", name="uq_book_word"),
        {"comment": "英语单词：词库内唯一，含音标/释义/难度/标签"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    book_id = Column(Integer, ForeignKey("word_books.id"), nullable=False, comment="所属词库 ID")
    word = Column(String(100), nullable=False, comment="英文单词")
    phonetic = Column(String(100), default="", comment="音标")
    pos = Column(String(20), default="", comment="词性 n./v./adj.等")
    meaning = Column(String(200), nullable=False, comment="中文释义")
    unit = Column(String(50), default="", comment="所属单元")
    difficulty = Column(Integer, default=1, comment="难度 1-5")
    tags = Column(String(200), default="", comment="标签，逗号分隔，如'动物,常见'")
    created_at = Column(DateTime, default=datetime.now, comment="入库时间")

    # 反向引用：经此访问所属词库（见上）
    book = relationship("WordBook", back_populates="words")

    def __repr__(self):
        return f"<Word {self.word} - {self.meaning}>"
