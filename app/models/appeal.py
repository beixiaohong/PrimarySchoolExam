"""孩子申诉模型：批改判错 → 孩子「我做对了」→ 家长二次确认（013 迁移建表）"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..database import Base


class AnswerAppeal(Base):
    """孩子对判错的申诉（家长二次确认后改判/维持）"""
    __tablename__ = "answer_appeals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    source = Column(String(20), nullable=False, default="exam")  # exam=在线做题 / retry=错题重练
    question_id = Column(Integer, nullable=True)
    record_id = Column(Integer, nullable=True)          # retry：错题记录 id
    record_kind = Column(String(20), nullable=True)     # retry：exam / study
    question = Column(Text, nullable=False)
    user_answer = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    subject = Column(String(20), nullable=False, default="")
    wrong_record_id = Column(Integer, nullable=True)    # exam：本次提交新建的错题记录 id（确认后删除）
    wrong_new = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="pending")  # pending / approved / rejected
    created_at = Column(DateTime, default=datetime.now)
    decided_at = Column(DateTime, nullable=True)
