"""Sprint 4 模型：挑战赛纪录 + 小老师讲解记录（对应迁移 007）"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, Text

from ..database import Base


class ChallengeRecord(Base):
    """限时挑战赛成绩纪录"""
    __tablename__ = "challenge_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # math 口算 / word 单词
    correct = Column(Integer, default=0)
    total = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class TeachingRecord(Base):
    """小老师模式：错题出题给家长 + 7 天复习验证

    状态机：pending（孩子讲解中，待家长作答）→ answered（家长已作答，待批改）
    → graded（批改完成，7 天后自动复习验证）→ recheck 后 recheck_status=passed/failed
    批改答错 → 重置回 pending 重新讲；7 天验证失败 → 重置回 pending 重新讲。
    """
    __tablename__ = "teaching_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    record_kind = Column(String(20), nullable=False)  # exam / study（错题来源）
    record_id = Column(Integer, nullable=False)  # WrongRecord.id / StudyError.id
    question = Column(Text, nullable=False)  # 题目快照
    answer = Column(Text, nullable=False)  # 正确答案快照
    note = Column(Text, default="")  # 孩子讲解要点（可选）
    status = Column(String(20), default="pending")  # pending/answered/graded
    answer_text = Column(Text, default="")
    is_correct = Column(Integer, nullable=True)  # 1 对 / 0 错
    created_at = Column(DateTime, default=datetime.now)
    answered_at = Column(DateTime, nullable=True)
    graded_at = Column(DateTime, nullable=True)
    due_date = Column(Date, nullable=True)  # 批改后 7 天的复习验证日
    recheck_status = Column(String(20), nullable=True)  # pending/passed/failed
