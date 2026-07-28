"""数学题型数据模型"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship

from ..database import Base


class ProblemCategory(Base):
    """题目大类（如：计算题、应用题、图形与几何）"""
    __tablename__ = "problem_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True, comment="大类名称")
    subject = Column(String(20), default="数学", comment="学科")
    description = Column(String(200), default="")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    problem_types = relationship("ProblemType", back_populates="category", cascade="all, delete-orphan")


class ProblemType(Base):
    """具体题型（如：分数四则运算、行程问题、面积计算）"""
    __tablename__ = "problem_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("problem_categories.id"), nullable=False)
    name = Column(String(80), nullable=False, comment="题型名称")
    code = Column(String(50), nullable=False, unique=True, comment="题型编码，用于生成器映射")
    difficulty_min = Column(Integer, default=1, comment="最低难度")
    difficulty_max = Column(Integer, default=5, comment="最高难度")
    grade_min = Column(Integer, default=1, comment="适用最低年级")
    grade_max = Column(Integer, default=6, comment="适用最高年级")
    params_schema = Column(Text, default="{}", comment="生成参数JSON Schema")
    is_active = Column(Boolean, default=True)
    weight = Column(Integer, default=10, comment="出题权重")
    description = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.now)

    category = relationship("ProblemCategory", back_populates="problem_types")

    def __repr__(self):
        return f"<ProblemType {self.code}: {self.name}>"
