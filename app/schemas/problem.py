"""数学题目相关 Schema"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ProblemTypeCreate(BaseModel):
    """新增数学题型请求体（写入契约）"""
    category_id: int  # 所属大类 ID
    name: str = Field(..., max_length=80)  # 题型名称
    code: str = Field(..., max_length=50)  # 题型代码（唯一标识，用于抽题）
    difficulty_min: int = Field(1, ge=1, le=5)  # 该题型难度下限
    difficulty_max: int = Field(5, ge=1, le=5)  # 该题型难度上限
    grade_min: int = Field(1, ge=1, le=6)  # 适用年级下限
    grade_max: int = Field(6, ge=1, le=6)  # 适用年级上限
    weight: int = Field(10, ge=1)  # 抽题权重（越大越易被抽中）
    description: str = ""  # 题型说明


class ProblemTypeOut(BaseModel):
    """数学题型响应契约"""
    id: int  # 主键
    category_id: int  # 所属大类 ID
    name: str  # 题型名称
    code: str  # 题型代码
    difficulty_min: int  # 难度下限
    difficulty_max: int  # 难度上限
    grade_min: int  # 年级下限
    grade_max: int  # 年级上限
    weight: int  # 抽题权重
    is_active: bool  # 是否启用
    description: str  # 说明

    model_config = ConfigDict(from_attributes=True)


class CategoryOut(BaseModel):
    """题型大类响应契约（含其下题型列表）"""
    id: int  # 大类主键
    name: str  # 大类名称
    subject: str  # 学科（如数学）
    description: str  # 说明
    is_active: bool  # 是否启用
    problem_types: List[ProblemTypeOut] = []  # 该大类下的题型列表

    model_config = ConfigDict(from_attributes=True)


class MathGenRequest(BaseModel):
    """数学题生成请求"""
    grade: int = Field(6, ge=1, le=9, description="年级")
    difficulty: str = Field("综合", description="难度：基础/提高/拔高/综合")
    categories: Optional[List[str]] = Field(None, description="指定大类名称列表，None=全部")
    problem_types: Optional[List[str]] = Field(None, description="指定题型code列表，None=按权重自动")
    count: int = Field(20, ge=1, le=500, description="总题数")
    include_answer: bool = Field(True, description="是否包含答案")
    output_format: str = Field("json", description="输出格式：json/docx")


class ProblemItem(BaseModel):
    """单道题目（数学题生成响应中的一项）"""
    id: int  # 题目 ID
    category: str  # 所属大类
    type_code: str = ""  # 题型代码
    type_name: str  # 题型名称
    difficulty: int  # 难度档
    question: str  # 题干
    answer: str = ""  # 答案（include_answer=False 时为空）
    exact_answer: str = ""  # 精确答案（根因修复：非整数结果存高精度值，如 10/3→'3.3333333333'）
    image_path: str = ""  # 配图路径（如有）


class MathGenResponse(BaseModel):
    """数学题生成响应契约"""
    total: int  # 题目总数
    difficulty: str  # 实际采用难度档
    grade: int  # 年级
    problems: List[ProblemItem]  # 题目列表
