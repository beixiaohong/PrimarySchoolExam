"""同步学模块数据模型"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Float

from ..database import Base


class SyncQuizLog(Base):
    """单元小测成绩记录（同步学，034 迁移建表；SQLite 测试靠 create_all）"""
    __tablename__ = "sync_quiz_log"
    __table_args__ = {"comment": "同步学单元小测成绩：记录每用户每科每单元的小测得分"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户 ID")
    subject = Column(String(20), nullable=False, index=True, comment="学科：语文/数学/英语")
    grade = Column(Integer, default=0, comment="年级")
    unit = Column(String(120), nullable=False, default="", comment="单元标识（英语=book::unit，语文=学期组，数学=教材章节）")
    score = Column(Float, default=0, comment="本次得分（满分 100）")
    total = Column(Integer, default=10, comment="题目总数")
    correct = Column(Integer, default=0, comment="答对题数")
    created_at = Column(DateTime, default=datetime.now, comment="提交时间")

    def __repr__(self):
        return f"<SyncQuizLog {self.user_id} {self.subject} {self.unit} {self.score}>"
