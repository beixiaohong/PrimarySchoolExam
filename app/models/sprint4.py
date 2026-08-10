"""Sprint 4 模型：挑战赛纪录 + 小老师讲解记录（对应迁移 007）"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, Text

from ..database import Base


class ChallengeRecord(Base):
    """限时挑战赛成绩纪录"""
    __tablename__ = "challenge_records"
    __table_args__ = {"comment": "限时挑战赛成绩：口算/单词速答，记录对错与题量"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    kind = Column(String(20), nullable=False, comment="挑战类型：math 口算 / word 单词")
    correct = Column(Integer, default=0, comment="答对题数")
    total = Column(Integer, default=0, comment="总题数")
    created_at = Column(DateTime, default=datetime.now, comment="完成时间")


class TeachingRecord(Base):
    """小老师模式：错题出题给家长 + 7 天复习验证

    状态机：pending（孩子讲解中，待家长作答）→ answered（家长已作答，待批改）
    → graded（批改完成，7 天后自动复习验证）→ recheck 后 recheck_status=passed/failed
    批改答错 → 重置回 pending 重新讲；7 天验证失败 → 重置回 pending 重新讲。
    """
    __tablename__ = "teaching_records"
    __table_args__ = {"comment": "小老师模式：孩子给家长讲错题，7 天后复习验证掌握情况"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True, comment="用户标识")
    record_kind = Column(String(20), nullable=False, comment="错题来源：exam / study")
    record_id = Column(Integer, nullable=False, comment="错题记录 ID（WrongRecord.id / StudyError.id）")
    question = Column(Text, nullable=False, comment="题目快照")
    answer = Column(Text, nullable=False, comment="正确答案快照")
    note = Column(Text, default="", comment="孩子讲解要点（可选）")
    status = Column(String(20), default="pending", comment="pending/answered/graded")
    answer_text = Column(Text, default="", comment="家长作答内容")
    is_correct = Column(Integer, nullable=True, comment="批改结果：1 对 / 0 错")
    created_at = Column(DateTime, default=datetime.now, comment="出题时间")
    answered_at = Column(DateTime, nullable=True, comment="家长作答时间")
    graded_at = Column(DateTime, nullable=True, comment="批改完成时间")
    due_date = Column(Date, nullable=True, comment="批改后 7 天的复习验证日")
    recheck_status = Column(String(20), nullable=True, comment="复习验证结果：pending/passed/failed")
