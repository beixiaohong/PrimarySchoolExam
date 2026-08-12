"""多 AI 联合校对记录模型（038 迁移建表；SQLite 测试靠 create_all）

记录每次校对：哪条内容、哪个 AI 供应商、判定结论与理由。
汇总规则（D6 决议）：
- 全部 pass → 内容 review_status=approved，可参与出题
- 存在 fail 或意见不一 → review_status=conflict，进管理后台人工审核队列
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from ..database import Base


class ContentReview(Base):
    """多 AI 联合校对记录（题库/阅读篇目/词句素材）"""
    __tablename__ = "content_reviews"
    __table_args__ = {"comment": "多 AI 联合校对记录：双供应商独立审阅，分歧进人工审核队列"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    content_type = Column(String(40), nullable=False, index=True, comment="内容类型：middle_question/reading_passage/phrase/sentence")
    content_id = Column(Integer, nullable=False, index=True, comment="被校对内容的主键 ID")
    provider = Column(String(20), default="", comment="AI 供应商：zhipu/relay/deepseek")
    model = Column(String(40), default="", comment="实际使用的模型名")
    verdict = Column(String(20), default="pass", comment="结论：pass/fail")
    comment = Column(Text, default="", comment="供应商给出的理由/修改建议")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<ContentReview {self.content_type}#{self.content_id} {self.provider}={self.verdict}>"
