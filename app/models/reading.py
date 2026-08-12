"""阅读理解专项数据模型（036 迁移建表；SQLite 测试靠 create_all）

questions_json 结构（每题）：
{
  "type": "choice" | "short",
  "question": "...",
  "options": ["A...", "B...", ...],   # choice 有，short 为空
  "answer": "正确选项文本 或 参考答案要点(短句)",
  "points": ["要点1", "要点2"],        # 主观题评分要点
  "score": 分值
}
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from ..database import Base


class ReadingPassage(Base):
    """阅读理解篇目（英语 7-9 / 语文小学高段+初中，种子版需人工校对）"""
    __tablename__ = "reading_passages"
    __table_args__ = {"comment": "阅读理解专项篇目：全文+结构化题目，支持客观即时判分与主观 AI 判分"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    subject = Column(String(20), nullable=False, index=True, comment="学科：语文/英语")
    grade = Column(Integer, default=0, comment="适用年级")
    semester = Column(String(10), default="全", comment="学期：上/下/全")
    title = Column(String(200), default="", comment="篇名")
    passage = Column(Text, default="", comment="阅读材料全文")
    questions_json = Column(Text, default="[]", comment="结构化题目 JSON 数组")
    review_status = Column(String(20), default="pending", comment="校对状态：pending/approved/conflict/rejected（038 多AI校对）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<ReadingPassage {self.subject} G{self.grade}: {self.title}>"
