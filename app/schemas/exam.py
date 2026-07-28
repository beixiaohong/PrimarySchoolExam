"""试卷生成相关 Schema"""
from typing import Optional, List
from pydantic import BaseModel, Field


class ExamCreateRequest(BaseModel):
    """试卷生成请求"""
    subject: str = Field(..., description="学科：数学/英语")
    title: Optional[str] = Field(None, description="试卷标题，不填则自动生成")
    grade: int = Field(6, ge=1, le=6)
    difficulty: str = Field("综合", description="基础/提高/拔高/综合")

    # 数学专用
    math_count: int = Field(30, ge=5, le=200, description="数学题数量")
    math_categories: Optional[List[str]] = Field(None, description="数学大类筛选")

    # 英语专用
    english_word_count: int = Field(50, ge=10, le=200, description="英语单词题数量")
    english_book_ids: Optional[List[int]] = Field(None, description="词库ID筛选")
    english_types: Optional[List[str]] = Field(
        None, description="英语题型：听写/选择/翻译/词组句"
    )


class ExamOut(BaseModel):
    id: int
    subject: str
    title: str
    grade: int
    difficulty: str
    question_count: int
    file_path: str
    created_at: str

    class Config:
        from_attributes = True
