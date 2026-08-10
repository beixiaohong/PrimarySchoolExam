"""学习练习错题记录模型

记录语法练习、古诗文默写等"学习模块"中答错的题目，
与试卷错题（WrongRecord）分开存储，通过 source_type 区分来源。
同一用户对同一道题只有一条记录（联合唯一约束），重复答错累计次数。
"""
from datetime import date, datetime

from sqlalchemy import Column, Integer, String, DateTime, Date, Text, Boolean, UniqueConstraint

from ..database import Base


class StudyError(Base):
    """用户学习模块错题记录

    source_type: grammar（语法练习）/ classical（古诗文默写）
    source_id:   对应模块内题目的ID（GrammarExercise.id / 随机题无固定ID时为0）
    """
    __tablename__ = "study_errors"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_user_source"),
        {"comment": "学习模块错题：语法练习/古诗文默写等答错题，与试卷错题分开存储"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, index=True,
                     comment="用户标识（如学生姓名/学号）")
    source_type = Column(String(20), nullable=False,
                         comment="来源：grammar / classical")
    source_id = Column(Integer, default=0, nullable=False,
                       comment="来源题目标识（grammar为题目ID）")

    # ── 题目内容快照 ──
    module_name = Column(String(50), default="",
                         comment="模块名，如：语法练习 / 古诗文默写")
    question = Column(Text, default="",
                      comment="题目文本快照")
    user_answer = Column(Text, default="",
                         comment="用户错误答案（最近一次）")
    correct_answer = Column(Text, default="",
                            comment="正确答案")
    explanation = Column(Text, default="",
                         comment="解析（如有）")

    # ── 状态 ──
    error_count = Column(Integer, default=1,
                         comment="累计答错次数")
    is_mastered = Column(Boolean, default=False,
                         comment="是否已掌握")
    correct_streak = Column(Integer, default=0,
                            comment="连续答对次数（达3次自动掌握）")
    cause = Column(String(20), default="",
                   comment="错因自评：careless(粗心)/concept(概念不清)/method(方法不会)/reading(审题失误)")
    next_review_date = Column(Date, nullable=True,
                              comment="明日复习队列：重做仍错 → 明天再来一次（014 迁移）")
    wrong_at = Column(DateTime, default=datetime.now,
                      comment="最近一次答错时间")
    mastered_at = Column(DateTime, nullable=True,
                         comment="标记已掌握时间")

    def __repr__(self):
        return (f"<StudyError user={self.user_id} "
                f"source={self.source_type}:{self.source_id} mastered={self.is_mastered}>")
