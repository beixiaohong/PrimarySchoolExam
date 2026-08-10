"""英语语法练习数据模型"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint

from ..database import Base


class GrammarPoint(Base):
    """语法点分类"""
    __tablename__ = "grammar_points"
    __table_args__ = (
        UniqueConstraint("code", name="uq_grammar_code"),
        {"comment": "英语语法点分类：时态/词法/句型/语态，含规则说明与例句"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    name = Column(String(100), nullable=False, comment="语法点名称，如：一般现在时")
    code = Column(String(50), nullable=False, unique=True, comment="唯一编码")
    grade = Column(Integer, nullable=False, comment="适用年级 3-6")
    category = Column(String(50), default="时态", comment="分类：时态/词法/句型/语态")
    description = Column(String(500), default="", comment="语法点说明/规则")
    examples = Column(Text, default="", comment="示例句子，每行一句")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<GrammarPoint {self.name} ({self.code})>"


class GrammarExercise(Base):
    """语法练习题"""
    __tablename__ = "grammar_exercises"
    __table_args__ = {"comment": "英语语法练习题：选择/填空/转换/改错等题型"}

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    grammar_point_id = Column(Integer, nullable=False, comment="所属语法点 ID（grammar_points.id）")
    grade = Column(Integer, nullable=False, comment="适用年级")
    exercise_type = Column(String(30), nullable=False, comment="题型：choice/fill/transform/correct")
    question = Column(String(500), nullable=False, comment="题目内容")
    options = Column(Text, default="", comment="选项（选择题用），JSON数组")
    answer = Column(String(200), nullable=False, comment="正确答案")
    explanation = Column(String(500), default="", comment="解析")
    difficulty = Column(Integer, default=1, comment="难度 1-5")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def __repr__(self):
        return f"<GrammarExercise {self.exercise_type} q{self.id}>"
