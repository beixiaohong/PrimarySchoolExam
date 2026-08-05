"""用户背单词进度模型（艾宾浩斯记忆曲线）"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, UniqueConstraint, Date

from ..database import Base


class VocabProgress(Base):
    """用户对每个单词的学习进度"""
    __tablename__ = "vocab_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "word_id", name="uq_user_word"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, comment="用户名")
    word_id = Column(Integer, ForeignKey("words.id"), nullable=False)

    # 状态: learning=学习中, mastered=已掌握
    status = Column(String(20), default="learning", comment="learning/mastered")

    # 艾宾浩斯曲线参数
    review_stage = Column(Integer, default=0, comment="当前复习阶段 0~5，对应6个间隔")
    next_review_date = Column(Date, nullable=True, comment="下次复习日期")
    last_review_date = Column(Date, nullable=True, comment="上次复习日期")
    first_learn_date = Column(Date, nullable=True, comment="首次学习日期")

    # 统计
    correct_count = Column(Integer, default=0, comment="累计答对次数")
    wrong_count = Column(Integer, default=0, comment="累计答错次数")
    total_reviews = Column(Integer, default=0, comment="总复习次数")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<VocabProgress user={self.user_id} word_id={self.word_id} stage={self.review_stage}>"


class VocabDailyLog(Base):
    """每日学习日志（记录每天学了多少新词、复习了多少）"""
    __tablename__ = "vocab_daily_log"
    __table_args__ = (
        UniqueConstraint("user_id", "learn_date", name="uq_user_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    learn_date = Column(Date, nullable=False, comment="学习日期")
    new_words_learned = Column(Integer, default=0, comment="当天新学单词数")
    words_reviewed = Column(Integer, default=0, comment="当天复习单词数")
    correct_count = Column(Integer, default=0, comment="当天答对数")
    wrong_count = Column(Integer, default=0, comment="当天答错数")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
