"""试卷生成记录"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text

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

    def __repr__(self):
        return f"<ExamRecord {self.title}>"
