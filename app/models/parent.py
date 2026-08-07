"""家长功能模型：密码 / 试卷最少题数 / 家长消息（011 迁移建表）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from ..database import Base


class ParentPassword(Base):
    """家长密码（按孩子 user_id 一份），密保用于忘记密码时重置"""
    __tablename__ = "parent_passwords"

    user_id = Column(String(50), primary_key=True)
    password_hash = Column(String(200), nullable=False)
    hint_question = Column(String(100), nullable=False)
    hint_answer_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ExamMinCount(Base):
    """每科试卷最少题数（生成试卷时强制下限）"""
    __tablename__ = "exam_min_counts"

    user_id = Column(String(50), primary_key=True)
    math_min = Column(Integer, default=5)
    chi_min = Column(Integer, default=5)
    eng_min = Column(Integer, default=5)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ParentMessage(Base):
    """家长发给孩子的留言"""
    __tablename__ = "parent_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    content = Column(String(300), nullable=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
