"""数学题目相关 Schema"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ProblemTypeCreate(BaseModel):
    category_id: int
    name: str = Field(..., max_length=80)
    code: str = Field(..., max_length=50)
    difficulty_min: int = Field(1, ge=1, le=5)
    difficulty_max: int = Field(5, ge=1, le=5)
    grade_min: int = Field(1, ge=1, le=6)
    grade_max: int = Field(6, ge=1, le=6)
    weight: int = Field(10, ge=1)
    description: str = ""


class ProblemTypeOut(BaseModel):
    id: int
    category_id: int
    name: str
    code: str
    difficulty_min: int
    difficulty_max: int
    grade_min: int
    grade_max: int
    weight: int
    is_active: bool
    description: str

    class Config:
        from_attributes = True


class CategoryOut(BaseModel):
    id: int
    name: str
    subject: str
    description: str
    is_active: bool
    problem_types: List[ProblemTypeOut] = []

    class Config:
        from_attributes = True


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
    """单道题目"""
    id: int
    category: str
    type_code: str = ""
    type_name: str
    difficulty: int
    question: str
    answer: str = ""
    image_path: str = ""


class MathGenResponse(BaseModel):
    total: int
    difficulty: str
    grade: int
    problems: List[ProblemItem]
