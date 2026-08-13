"""作文 / 简答判分数据模型（035 迁移建表；测试库靠 create_all 兜底）"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Float

from ..database import Base


class EssayGrade(Base):
    """作文批改评分卡（按学段评分制，前端可回看历次对比）"""
    __tablename__ = "essay_grades"
    __table_args__ = {"comment": "作文批改记录：评分卡 JSON + 原文，支持历次回看"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户 ID")
    subject = Column(String(20), nullable=False, comment="学科：语文/英语")
    grade = Column(Integer, default=6, comment="年级（决定学段满分）")
    topic = Column(String(200), default="", comment="作文题目")
    content = Column(Text, default="", comment="学生作文原文（≤800 字）")
    score_json = Column(Text, default="{}", comment="评分卡 JSON：total/四维分项/亮点/改进/升格示例")
    created_at = Column(DateTime, default=datetime.now, comment="提交时间")

    def __repr__(self):
        return f"<EssayGrade {self.user_id} {self.subject} {self.topic}>"
