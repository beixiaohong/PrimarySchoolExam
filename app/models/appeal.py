"""孩子申诉模型：批改判错 → 孩子「我做对了」→ 家长二次确认（013 迁移建表）"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..database import Base


class AnswerAppeal(Base):
    """孩子对判错的申诉（家长二次确认后改判/维持）"""
    __tablename__ = "answer_appeals"
    __table_args__ = {"comment": "答案申诉：孩子对判错发起「我做对了」，家长二次确认后改判/维持"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(50), nullable=False, index=True, comment="用户名")
    source = Column(String(20), nullable=False, default="exam", comment="来源：exam=在线做题 / retry=错题重练")
    question_id = Column(Integer, nullable=True, comment="题目 ID（如有）")
    record_id = Column(Integer, nullable=True, comment="retry：错题记录 id")
    record_kind = Column(String(20), nullable=True, comment="retry：错题来源 exam / study")
    question = Column(Text, nullable=False, comment="题目快照")
    user_answer = Column(Text, nullable=False, comment="孩子的答案")
    correct_answer = Column(Text, nullable=False, comment="判定的正确答案")
    subject = Column(String(20), nullable=False, default="", comment="学科")
    wrong_record_id = Column(Integer, nullable=True, comment="exam：本次提交新建的错题记录 id（确认后删除）")
    wrong_new = Column(Boolean, nullable=False, default=False, comment="是否新建了错题记录")
    # status 取值：pending=待家长裁决，approved=改判（认定孩子答对），rejected=维持原判
    status = Column(String(20), nullable=False, default="pending", comment="pending / approved / rejected")
    created_at = Column(DateTime, default=datetime.now, comment="申诉发起时间")
    decided_at = Column(DateTime, nullable=True, comment="家长裁决时间")
