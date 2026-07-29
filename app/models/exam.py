"""试卷与题目数据模型

ExamRecord:   试卷生成记录（一份试卷可给多人使用，不绑定用户）
Question:     试卷中的每道题（生成时自动入库，属于试卷本身）
WrongRecord:  用户错题记录（哪个用户把哪道题标记为错题，支持多用户独立错题本）
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class ExamRecord(Base):
    """试卷生成记录

    一份试卷是公共资源，不绑定用户。
    任何用户都可以对同一份试卷中的题目标记错题。
    """
    __tablename__ = "exam_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject = Column(String(20), nullable=False,
                     comment="学科：数学 / 英语")
    title = Column(String(200), nullable=False,
                   comment="试卷标题")
    grade = Column(Integer, default=6,
                   comment="年级 1-6")
    difficulty = Column(String(20), default="综合",
                        comment="难度：基础 / 提高 / 拔高 / 综合")
    config_json = Column(Text, default="{}",
                         comment="生成时的完整请求参数JSON，便于复现")
    file_path = Column(String(500), default="",
                       comment="生成的Word文件绝对路径")
    question_count = Column(Integer, default=0,
                            comment="本卷题目总数")
    created_at = Column(DateTime, default=datetime.now,
                        comment="生成时间")

    questions = relationship("Question", back_populates="exam",
                             cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ExamRecord id={self.id} title={self.title}>"


class Question(Base):
    """试卷中的每道题目

    属于试卷本身，不绑定用户。
    错题标记通过 WrongRecord 表按用户独立记录。
    """
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exam_records.id"), nullable=False,
                     comment="所属试卷ID")
    seq = Column(Integer, nullable=False,
                 comment="题目在试卷内的序号（从1开始）")

    # ── 题目分类信息 ──
    subject = Column(String(20), nullable=False,
                     comment="学科：数学 / 英语")
    category = Column(String(50), default="",
                      comment="大类名称（数学：计算题/图形与几何/…；英语：英语）")
    type_code = Column(String(50), default="",
                       comment="题型代码（如 calc_int_basic / phrase_translation）")
    type_name = Column(String(50), default="",
                       comment="题型中文名（如 整数四则运算 / 词组翻译）")

    # ── 题目内容 ──
    question = Column(Text, nullable=False,
                      comment="题目文本")
    answer = Column(Text, default="",
                    comment="参考答案")
    options_json = Column(Text, default="",
                          comment="选项JSON数组（选择题有值，非选择题为空串）")
    difficulty = Column(Integer, default=1,
                        comment="难度等级 1-5")

    created_at = Column(DateTime, default=datetime.now,
                        comment="入库时间")

    exam = relationship("ExamRecord", back_populates="questions")
    wrong_records = relationship("WrongRecord", back_populates="question",
                                 cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Question id={self.id} exam={self.exam_id} seq={self.seq}>"


class WrongRecord(Base):
    """用户错题记录

    记录"哪个用户"把"哪道题"标记为错题。
    同一用户对同一道题只有一条记录（联合唯一约束）。
    支持：练习次数统计、标记已掌握。
    """
    __tablename__ = "wrong_records"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_question"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True,
                     comment="用户标识（如学生姓名/学号）")
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False,
                         comment="题目ID")

    # ── 错题状态 ──
    is_mastered = Column(Boolean, default=False,
                         comment="是否已掌握（掌握后错题练习不再抽取）")
    practice_count = Column(Integer, default=0,
                            comment="该题被纳入错题练习的累计次数")

    # ── 时间记录 ──
    wrong_at = Column(DateTime, default=datetime.now,
                      comment="标记为错题的时间")
    mastered_at = Column(DateTime, nullable=True,
                         comment="标记已掌握的时间")

    question = relationship("Question", back_populates="wrong_records")

    def __repr__(self):
        return (f"<WrongRecord user={self.user_id} "
                f"question={self.question_id} mastered={self.is_mastered}>")
