"""试卷生成记录"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base


class ExamRecord(Base):
    """试卷生成记录"""
    __tablename__ = "exam_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String(20), nullable=False, comment="学科：数学/英语")
    title = Column(String(200), nullable=False, comment="试卷标题")
    grade = Column(Integer, default=6, comment="年级")
    difficulty = Column(String(20), default="综合", comment="难度：基础/提高/拔高/综合")
    config_json = Column(Text, default="{}", comment="生成配置JSON")
    file_path = Column(String(500), default="", comment="生成的文件路径")
    question_count = Column(Integer, default=0, comment="题目数量")
    created_at = Column(DateTime, default=datetime.now)

    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ExamRecord {self.title}>"


class Question(Base):
    """试卷中的每道题目"""
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exam_records.id"), nullable=False, comment="所属试卷")
    seq = Column(Integer, nullable=False, comment="题目序号（试卷内）")
    subject = Column(String(20), nullable=False, comment="学科：数学/英语")
    category = Column(String(50), default="", comment="大类（如：计算题/图形与几何）")
    type_code = Column(String(50), default="", comment="题型代码（如：calc_int_basic）")
    type_name = Column(String(50), default="", comment="题型名称（如：整数四则运算）")
    question = Column(Text, nullable=False, comment="题目内容")
    answer = Column(Text, default="", comment="参考答案")
    options_json = Column(Text, default="", comment="选项JSON（选择题）")
    difficulty = Column(Integer, default=1, comment="难度 1-5")
    is_wrong = Column(Boolean, default=False, comment="是否标记为错题")
    wrong_at = Column(DateTime, nullable=True, comment="标记错题时间")
    created_at = Column(DateTime, default=datetime.now)

    exam = relationship("ExamRecord", back_populates="questions")

    def __repr__(self):
        return f"<Question exam={self.exam_id} seq={self.seq} wrong={self.is_wrong}>"
